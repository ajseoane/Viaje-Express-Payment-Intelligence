import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from payments.adapters import ADAPTERS, normalize, money
from payments.generate import generate
from payments.pipeline import ingest


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw, self.out = self.root / 'raw', self.root / 'out'
        generate(self.raw)

    def tearDown(self):
        self.temp.cleanup()

    def test_full_load_and_idempotency(self):
        records, summary = ingest(self.raw, self.out)
        self.assertEqual((len(records), summary['duplicates'], summary['rejected']), (1422, 6, 18))
        self.assertEqual(set(r['country'] for r in records), {'MX', 'BR', 'AR', 'CO', 'ES', 'PT'})
        self.assertEqual(len(set(r['currency'] for r in records)), 5)
        self.assertEqual(len(set(r['psp'] for r in records)), 6)
        self.assertTrue(all(r['timestamp'].endswith('Z') for r in records))
        self.assertTrue(any(r['fee_minor'] is None for r in records))
        again, summary = ingest(self.raw, self.out)
        self.assertEqual(summary['inserted'], 0)
        self.assertEqual(summary['duplicates'], 1428)
        self.assertEqual(len(again), 1422)
        self.assertEqual(len(list((self.out / 'evidence').iterdir())), 6)

    def test_conflicting_snapshot_is_quarantined(self):
        ingest(self.raw, self.out)
        path = self.raw / 'psp1.json'
        records = json.loads(path.read_text(encoding='utf-8'))
        records[1]['amount'] = '999.99'
        path.write_text(json.dumps(records), encoding='utf-8')
        _, summary = ingest(self.raw, self.out)
        self.assertEqual(summary['rejected'], 19)
        errors = json.loads((self.out / 'quarantine.json').read_text())
        self.assertTrue(any('Conflicting snapshot' in r['reason'] for r in errors))

    def test_money_precision(self):
        self.assertEqual(money('1.234,56', ADAPTERS['PSP2']), 123456)
        self.assertEqual(money('0.10', ADAPTERS['PSP1']), 10)
        self.assertEqual(money('101', ADAPTERS['PSP6']), 101)
        for value in ['NaN', 'Infinity', '-1', '1.001']:
            with self.assertRaises(ValueError):
                money(value, ADAPTERS['PSP1'])

    def test_explicit_timezone_status_and_currency(self):
        raw = json.loads((self.raw / 'psp1.json').read_text(encoding='utf-8'))[1]
        raw['created_at'] = '2026-09-01T01:00:00+02:00'
        self.assertEqual(normalize('PSP1', raw)['timestamp'], '2026-08-31T23:00:00Z')
        for field, value in [('created_at', '2026-09-01T01:00:00'), ('currency', 'USD'), ('status', 'new_status')]:
            bad = dict(raw, **{field: value})
            with self.assertRaises(ValueError):
                normalize('PSP1', bad)

    def test_bad_jsonl_record_does_not_stop_other_rows(self):
        with (self.raw / 'psp6.jsonl').open('a', encoding='utf-8') as handle:
            handle.write('{broken\n')
        records, summary = ingest(self.raw, self.out)
        self.assertEqual(len(records), 1422)
        self.assertEqual(summary['rejected'], 19)

    def test_queryable_evidence(self):
        ingest(self.raw, self.out)
        with closing(sqlite3.connect(self.out / 'payments.sqlite')) as db:
            row = db.execute('SELECT source_sha256,raw_json,amount_minor FROM transactions LIMIT 1').fetchone()
            self.assertEqual(len(row[0]), 64)
            self.assertIsInstance(json.loads(row[1]), dict)
            self.assertIsInstance(row[2], int)


if __name__ == '__main__':
    unittest.main()
