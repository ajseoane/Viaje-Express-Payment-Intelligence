"""Provider contracts. Add an Adapter and a manifest entry to support another PSP.

Date and decimal conventions are explicit per provider; never guess ambiguous dates.
Amounts and fees are in the transaction's currency, in major units at the boundary.
"""
from dataclasses import dataclass
import csv
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Adapter:
    fields: dict
    statuses: dict
    date_format: str
    decimal_comma: bool = False
    minor_units: bool = False


ADAPTERS = {
    'PSP1': Adapter(dict(id='transaction_id', timestamp='created_at', amount='amount', currency='currency', country='country', method='payment_method', status='status', fee='fee'),
                    {'SUCCESS': 'approved', 'FAILED': 'declined', 'WAIT': 'pending', 'REFUND': 'refunded'}, 'iso'),
    'PSP2': Adapter(dict(id='id', timestamp='data', amount='valor', currency='moeda', country='pais', method='metodo', status='situacao', fee='taxa'),
                    {'PAGO': 'approved', 'RECUSADO': 'declined', 'AGUARDANDO': 'pending', 'ESTORNADO': 'refunded'}, '%d/%m/%Y %H:%M:%S%z', True),
    'PSP3': Adapter(dict(id='reference', timestamp='epoch', amount='total_value', currency='ccy', country='market', method='instrument', status='result', fee='processing_cost'),
                    {'00': 'approved', '05': 'declined', '09': 'pending', 'R': 'refunded'}, 'unix'),
    'PSP4': Adapter(dict(id='paymentId', timestamp='bookedAt', amount='gross', currency='currencyCode', country='countryCode', method='type', status='state', fee='cost'),
                    {'approved': 'approved', 'rejected': 'declined', 'pending': 'pending', 'refunded': 'refunded'}, '%d.%m.%Y %H:%M:%S%z', True),
    'PSP5': Adapter(dict(id='ref', timestamp='time', amount='transaction_amount', currency='currency_name', country='region', method='channel', status='outcome', fee='charge'),
                    {'COMPLETED': 'approved', 'DENIED': 'declined', 'OPEN': 'pending', 'RETURNED': 'refunded'}, 'iso'),
    'PSP6': Adapter(dict(id='event_id', timestamp='timestamp', amount='amount_minor', currency='currency', country='country', method='wallet', status='code', fee='fee_minor'),
                    {'200': 'approved', '402': 'declined', '102': 'pending', '299': 'refunded'}, 'unix', minor_units=True),
}

COUNTRIES = {'mexico': 'MX', 'méxico': 'MX', 'brazil': 'BR', 'brasil': 'BR', 'argentina': 'AR', 'colombia': 'CO', 'spain': 'ES', 'españa': 'ES', 'portugal': 'PT'}
MARKET_CURRENCY = {'MX': 'MXN', 'BR': 'BRL', 'AR': 'ARS', 'CO': 'COP', 'ES': 'EUR', 'PT': 'EUR'}
CURRENCIES = {'mexican peso': 'MXN', 'real': 'BRL', 'r$': 'BRL', 'argentine peso': 'ARS', 'colombian peso': 'COP', 'euro': 'EUR', '€': 'EUR'}
METHODS = {'credit card': 'credit_card', 'credit_card': 'credit_card', 'cc': 'credit_card', 'debit card': 'debit_card', 'debit_card': 'debit_card', 'dc': 'debit_card', 'pix': 'pix', 'boleto': 'boleto', 'oxxo': 'oxxo', 'bank transfer': 'bank_transfer', 'bank_transfer': 'bank_transfer', 'transfer': 'bank_transfer', 'wallet': 'digital_wallet', 'digital_wallet': 'digital_wallet'}


def read_records(path, format):
    """Yield 1-based record numbers, parsed row, and optional row-level parse error."""
    if format == 'csv':
        with path.open(encoding='utf-8-sig', newline='') as handle:
            for n, row in enumerate(csv.DictReader(handle), 1):
                yield n, row, None
    elif format == 'json':
        rows = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(rows, list):
            raise ValueError('JSON source must contain an array')
        for n, row in enumerate(rows, 1):
            yield n, row, None
    elif format == 'jsonl':
        for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            try:
                yield n, json.loads(line), None
            except json.JSONDecodeError as exc:
                yield n, {'unparsed_line': line}, str(exc)
    elif format == 'xml':
        root = ET.fromstring(path.read_text(encoding='utf-8'))
        for n, item in enumerate(root.findall('payment'), 1):
            yield n, {child.tag: child.text for child in item}, None
    else:
        raise ValueError(f'Unsupported source format: {format}')


def money(value, adapter):
    if isinstance(value, bool):
        raise ValueError('Boolean is not an amount')
    text = str(value).strip()
    if adapter.decimal_comma:
        text = text.replace('.', '').replace(',', '.')
    try:
        number = Decimal(text)
        if not number.is_finite() or number < 0:
            raise ValueError('Amount must be finite and nonnegative')
        minor = number if adapter.minor_units else number * 100
        if minor != minor.to_integral_value():
            raise ValueError('Amount has unsupported fractional minor units')
        if minor > 9_000_000_000_000_000:
            raise ValueError('Amount exceeds supported precision')
        return int(minor)
    except InvalidOperation as exc:
        raise ValueError(f'Invalid monetary amount: {value!r}') from exc


def normalize(psp, raw):
    adapter = ADAPTERS[psp]
    if not isinstance(raw, dict):
        raise ValueError('Record must be an object')
    fields = {key: raw.get(source) for key, source in adapter.fields.items()}
    required = ['id', 'timestamp', 'amount', 'currency', 'country', 'method', 'status']
    missing = [key for key in required if fields[key] is None or str(fields[key]).strip() == '']
    if missing:
        raise ValueError('Missing required fields: ' + ', '.join(missing))
    notes = []
    country_raw = str(fields['country']).strip()
    country = COUNTRIES.get(country_raw.lower(), country_raw.upper())
    if country not in MARKET_CURRENCY:
        raise ValueError('Unknown market: ' + country)
    currency_raw = str(fields['currency']).strip()
    currency = CURRENCIES.get(currency_raw.lower(), currency_raw.upper())
    # These simulated contracts explicitly specify local presentment currency.
    if currency == '$':
        currency = MARKET_CURRENCY[country]
        notes.append('currency_symbol_resolved_from_market_contract')
    if currency not in set(MARKET_CURRENCY.values()):
        raise ValueError('Unsupported or unknown currency: ' + currency)
    if currency != MARKET_CURRENCY[country]:
        raise ValueError('Currency conflicts with local-presentment contract')
    method = METHODS.get(str(fields['method']).strip().lower())
    if not method:
        raise ValueError('Unknown payment method')
    status = adapter.statuses.get(str(fields['status']).strip())
    if status is None:
        raise ValueError('Unknown provider status')
    time_value = str(fields['timestamp']).strip()
    try:
        if adapter.date_format == 'unix':
            dt = datetime.fromtimestamp(int(time_value), timezone.utc)
        elif adapter.date_format == 'iso':
            dt = datetime.fromisoformat(time_value.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(time_value, adapter.date_format)
        if dt.tzinfo is None:
            raise ValueError('Timestamp must contain an explicit timezone')
        timestamp = dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except (ValueError, OverflowError, OSError) as exc:
        raise ValueError('Malformed or timezone-ambiguous timestamp') from exc
    fee = fields['fee']
    fee_minor = None if fee is None or str(fee).strip() == '' else money(fee, adapter)
    if fee_minor is None:
        notes.append('fee_missing')
    provider_id = str(fields['id']).strip()
    return dict(id=f'{psp}:{provider_id}', provider_id=provider_id, psp=psp,
                timestamp=timestamp, amount_minor=money(fields['amount'], adapter),
                currency=currency, country=country, method=method, status=status,
                fee_minor=fee_minor, quality_notes=notes)
