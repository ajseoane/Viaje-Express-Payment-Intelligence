"""Idempotent load into SQLite with quarantine and immutable source snapshots."""
import csv
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from .adapters import ADAPTERS, read_records, normalize

SCHEMA = '''
CREATE TABLE IF NOT EXISTS transactions (
 id TEXT PRIMARY KEY, provider_id TEXT NOT NULL, psp TEXT NOT NULL,
 timestamp TEXT NOT NULL, amount_minor INTEGER NOT NULL, currency TEXT NOT NULL,
 country TEXT NOT NULL, method TEXT NOT NULL, status TEXT NOT NULL,
 fee_minor INTEGER, quality_notes TEXT NOT NULL, source_file TEXT NOT NULL,
 source_row INTEGER NOT NULL, source_sha256 TEXT NOT NULL,
 record_sha256 TEXT NOT NULL, raw_json TEXT NOT NULL, ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_filters ON transactions(timestamp, country, psp, method);
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, started_at TEXT, summary_json TEXT);
CREATE TABLE IF NOT EXISTS quarantine (
 id INTEGER PRIMARY KEY, run_id INTEGER, psp TEXT, source_file TEXT, source_row INTEGER,
 source_sha256 TEXT, reason TEXT, raw_json TEXT
);
'''


def ingest(raw_dir: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    evidence = output / 'evidence'
    evidence.mkdir(exist_ok=True)
    manifest = json.loads((raw_dir / 'manifest.json').read_text(encoding='utf-8'))
    now = datetime.now(timezone.utc).isoformat()
    summary = {'started_at': now, 'sources': [], 'inserted': 0, 'duplicates': 0, 'rejected': 0}
    with closing(sqlite3.connect(output / 'payments.sqlite')) as db, db:
        db.executescript(SCHEMA)
        run_id = db.execute('INSERT INTO runs(started_at) VALUES (?)', (now,)).lastrowid
        for source in manifest:
            psp, filename, fmt = source['psp'], source['file'], source['format']
            if psp not in ADAPTERS:
                raise ValueError(f'No adapter for {psp}')
            path = (raw_dir / filename).resolve()
            if not path.is_relative_to(raw_dir.resolve()):
                raise ValueError('Manifest file must stay within raw directory')
            file_bytes = path.read_bytes()
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            snapshot = evidence / (file_hash + path.suffix)
            if not snapshot.exists():
                snapshot.write_bytes(file_bytes)
            stats = dict(psp=psp, file=filename, rows=0, inserted=0, duplicates=0, rejected=0, missing_fees=0, warnings=0)
            def reject(n, raw, reason):
                stats['rejected'] += 1
                db.execute('INSERT INTO quarantine(run_id,psp,source_file,source_row,source_sha256,reason,raw_json) VALUES (?,?,?,?,?,?,?)',
                           (run_id, psp, filename, n, file_hash, reason, json.dumps(raw, ensure_ascii=False)))
            try:
                for n, raw, parse_error in read_records(path, fmt):
                    stats['rows'] += 1
                    try:
                        if parse_error:
                            raise ValueError('Malformed record: ' + parse_error)
                        tx = normalize(psp, raw)
                        canonical = json.dumps(tx, sort_keys=True, ensure_ascii=False)
                        record_hash = hashlib.sha256(canonical.encode()).hexdigest()
                        existing = db.execute('SELECT record_sha256 FROM transactions WHERE id=?', (tx['id'],)).fetchone()
                        if existing:
                            if existing[0] == record_hash:
                                stats['duplicates'] += 1
                                continue
                            raise ValueError('Conflicting snapshot for existing transaction ID; manual review required')
                        stats['missing_fees'] += tx['fee_minor'] is None
                        stats['warnings'] += bool(tx['quality_notes'])
                        tx['quality_notes'] = json.dumps(tx['quality_notes'])
                        tx.update(source_file=filename, source_row=n, source_sha256=file_hash, record_sha256=record_hash,
                                  raw_json=json.dumps(raw, ensure_ascii=False), ingested_at=now)
                        columns = ','.join(tx)
                        db.execute(f'INSERT INTO transactions({columns}) VALUES ({",".join("?" for _ in tx)})', tuple(tx.values()))
                        stats['inserted'] += 1
                    except (ValueError, TypeError, KeyError) as exc:
                        reject(n, raw, str(exc))
            except (ValueError, csv.Error) as exc:
                reject(0, {'file': filename}, 'File parse error: ' + str(exc))
            except Exception as exc:
                # XML errors are whole-file failures; unexpected programming errors remain fatal.
                import xml.etree.ElementTree as ET
                if isinstance(exc, ET.ParseError):
                    reject(0, {'file': filename}, 'XML parse error: ' + str(exc))
                else:
                    raise
            stats['validity_pct'] = round(100 * max(0, stats['rows'] - stats['rejected']) / stats['rows'], 2) if stats['rows'] else 0
            stats['fee_completeness_pct'] = round(100 * (stats['inserted'] - stats['missing_fees']) / stats['inserted'], 2) if stats['inserted'] else None
            summary['sources'].append(stats)
            for key in ['inserted', 'duplicates', 'rejected']:
                summary[key] += stats[key]
        summary['total_transactions'] = db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        db.execute('UPDATE runs SET summary_json=? WHERE id=?', (json.dumps(summary), run_id))
        db.row_factory = sqlite3.Row
        records = [dict(row) for row in db.execute('SELECT * FROM transactions ORDER BY timestamp,id')]
        for row in records:
            row['quality_notes'] = json.loads(row['quality_notes'])
        (output / 'transactions.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        with (output / 'transactions.csv').open('w', newline='', encoding='utf-8') as handle:
            cols = [d[1] for d in db.execute('PRAGMA table_info(transactions)')]
            writer = csv.DictWriter(handle, fieldnames=cols)
            writer.writeheader()
            writer.writerows(records)
        rejected = [dict(row) for row in db.execute('SELECT * FROM quarantine WHERE run_id=?', (run_id,))]
        (output / 'quarantine.json').write_text(json.dumps(rejected, ensure_ascii=False, indent=2), encoding='utf-8')
        (output / 'quality.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return records, summary
