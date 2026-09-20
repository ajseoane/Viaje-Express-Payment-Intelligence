"""Standalone dashboard and a short, reproducible weekly report."""
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def dashboard(records, quality, output):
    here = Path(__file__).parent
    payload = json.dumps(dict(transactions=records, quality=quality), ensure_ascii=False).replace('<', '\\u003c')
    template = (here / 'dashboard.html').read_text(encoding='utf-8')
    html = template.replace('__DATA__', payload).replace('__METRICS__', (here / 'metrics.js').read_text(encoding='utf-8'))
    (output / 'dashboard.html').write_text(html, encoding='utf-8')
    return html


def weekly_report(records, output):
    if not records:
        (output / 'weekly-report.md').write_text('# Weekly payment report\n\nNo transactions available.\n', encoding='utf-8')
        return
    last_day = max(r['timestamp'][:10] for r in records)
    start = (datetime.fromisoformat(last_day) - timedelta(days=6)).date().isoformat()
    week = [r for r in records if start <= r['timestamp'][:10] <= last_day]
    lines = ['# Weekly payment performance', '', f'Synthetic data · {start} through {last_day} (UTC)', '',
             f'{len(week)} payment attempts. Rates exclude pending; refunded payments count as earlier successes.', '',
             '| PSP / market | Final card decisions | Card authorization | All-method success |', '|---|---:|---:|---:|']
    groups = defaultdict(list)
    for r in week:
        groups[(r['psp'], r['country'])].append(r)
    def rate(rs):
        return f'{100 * sum(r["status"] in ("approved", "refunded") for r in rs) / len(rs):.1f}%' if rs else 'N/A'
    for (psp, country), rs in sorted(groups.items()):
        decided = [r for r in rs if r['status'] != 'pending']
        cards = [r for r in decided if r['method'] in ('credit_card', 'debit_card')]
        lines.append(f'| {psp} / {country} | {len(cards)} | {rate(cards)} | {rate(decided)} |')
    lines += ['', '| Currency | Gross TPV | Full refunds | Known successful fees | Fee coverage |', '|---|---:|---:|---:|---:|']
    for currency in sorted(set(r['currency'] for r in week)):
        paid = [r for r in week if r['currency'] == currency and r['status'] in ('approved', 'refunded')]
        known = [r for r in paid if r['fee_minor'] is not None]
        gross = sum(r['amount_minor'] for r in paid) / 100
        refunds = sum(r['amount_minor'] for r in paid if r['status'] == 'refunded') / 100
        fees = sum(r['fee_minor'] for r in known) / 100
        lines.append(f'| {currency} | {gross:,.2f} | {refunds:,.2f} | {fees:,.2f} | {len(known)}/{len(paid)} |')
    lines += ['', 'Currencies are never added together. Refunds use the original attempt date. This is payment-volume analysis, not bank settlement reconciliation.', '']
    (output / 'weekly-report.md').write_text('\n'.join(lines), encoding='utf-8')
