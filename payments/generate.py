"""Deterministic, synthetic 90-day data; no card or personal data."""
import csv
import json
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .adapters import ADAPTERS, MARKET_CURRENCY


def generate(target: Path):
    target.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20260920)
    markets = {'PSP1': ['MX', 'CO'], 'PSP2': ['BR'], 'PSP3': ['AR'], 'PSP4': ['ES', 'PT'], 'PSP5': ['MX', 'BR', 'AR', 'CO', 'ES', 'PT'], 'PSP6': ['MX', 'BR', 'AR', 'CO', 'ES', 'PT']}
    methods = {'PSP1': ['credit_card', 'debit_card'], 'PSP2': ['pix', 'boleto'], 'PSP3': ['credit_card', 'debit_card', 'bank_transfer'], 'PSP4': ['credit_card', 'debit_card', 'bank_transfer'], 'PSP5': ['bank_transfer'], 'PSP6': ['digital_wallet']}
    formats = ['json', 'csv', 'jsonl', 'xml', 'csv', 'jsonl']
    currency_names = {'MXN': 'Mexican Peso', 'BRL': 'Real', 'ARS': 'Argentine Peso', 'COP': 'Colombian Peso', 'EUR': 'Euro'}
    multipliers = {'MXN': 20, 'BRL': 6, 'ARS': 1200, 'COP': 4000, 'EUR': 1}
    manifest = []
    for provider_no, (psp, adapter) in enumerate(ADAPTERS.items()):
        rows = []
        for i in range(240):
            country = markets[psp][i % len(markets[psp])]
            currency = MARKET_CURRENCY[country]
            dt = datetime(2026, 6, 22, tzinfo=timezone.utc) + timedelta(days=(i * 7 + provider_no * 3) % 90, seconds=rng.randrange(86400))
            status = rng.choices(['approved', 'declined', 'pending', 'refunded'], [80, 15, 3, 2])[0]
            # A genuine seeded comparison signal for the final seven days.
            if psp == 'PSP1' and country == 'MX' and dt.date().isoformat() >= '2026-09-13':
                status = rng.choice(['approved', 'declined', 'declined'])
            method = rng.choice(methods[psp])
            if psp == 'PSP5':
                method = rng.choice(['bank_transfer', 'oxxo'] if country == 'MX' else ['pix', 'boleto'] if country == 'BR' else ['bank_transfer'])
            amount = rng.randint(4000, 95000) * multipliers[currency]
            fee = round(amount * [0.027, 0.009, 0.034, 0.019, 0.023, 0.029][provider_no]) + 20
            def format_money(value):
                if adapter.minor_units:
                    return value
                s = f'{value // 100}.{value % 100:02d}'
                return s.replace('.', ',') if adapter.decimal_comma else s
            stamp = int(dt.timestamp()) if adapter.date_format == 'unix' else dt.isoformat() if adapter.date_format == 'iso' else dt.astimezone(timezone(timedelta(hours=-3 if psp == 'PSP2' else 2))).strftime(adapter.date_format)
            values = dict(id=f'txn-{i+1:05}', timestamp=stamp, amount=format_money(amount), currency=currency,
                          country=country, method=method, status=next(key for key, val in adapter.statuses.items() if val == status), fee=format_money(fee))
            if i % 9 == 0:
                values['currency'] = currency_names[currency]
            if i % 13 == 0 and currency != 'EUR':
                values['currency'] = '$'
            if i % 11 == 0:
                values['method'] = method.upper()
            if i % 19 == 0:
                values['fee'] = ''
            # Three deliberately bad rows per PSP, each fails for a different reason.
            if i == 7:
                values['timestamp'] = '32/13/2026'
            if i == 17:
                values['amount'] = ''
            if i == 27:
                values['status'] = 'UNRECOGNIZED'
            rows.append({adapter.fields[k]: value for k, value in values.items()})
        rows.append(dict(rows[0]))  # duplicate delivery, not a new transaction
        fmt = formats[provider_no]
        filename = psp.lower() + '.' + fmt
        path = target / filename
        if fmt == 'json':
            path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
        elif fmt == 'jsonl':
            path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows) + '\n', encoding='utf-8')
        elif fmt == 'csv':
            with path.open('w', newline='', encoding='utf-8') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(adapter.fields.values()))
                writer.writeheader()
                writer.writerows(rows)
        else:
            root = ET.Element('payments')
            for row in rows:
                element = ET.SubElement(root, 'payment')
                for key, value in row.items():
                    ET.SubElement(element, key).text = str(value)
            ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
        manifest.append(dict(psp=psp, file=filename, format=fmt))
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return 1446
