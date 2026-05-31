"""
Reconciliation Engine
  - parse_in_memory(file_obj, category, session, user) : parse InMemoryUploadedFile, create transactions + log
  - run_reconciliation(session)                        : match bank vs ledger, create exceptions
"""
import csv
import io
from decimal import Decimal, InvalidOperation
from datetime import datetime
from difflib import SequenceMatcher

from .models import Transaction, FileUploadLog, Exception as ExceptionModel


# ─── Parsing ──────────────────────────────────────────────────────────────────

def parse_in_memory(django_file, category, session, user):
    """
    Read a Django InMemoryUploadedFile (or TemporaryUploadedFile) directly —
    never writes to disk. Returns (rows_extracted, error_message).
    """
    source_map = {
        'bank_statement': 'bank',
        'internal_ledger': 'ledger',
        'payment_gateway': 'payment',
    }
    source = source_map.get(category, 'bank')
    filename = django_file.name

    # Create a metadata log entry (no file stored)
    log = FileUploadLog.objects.create(
        session=session,
        original_filename=filename,
        category=category,
        status='processed',
        uploaded_by=user,
    )

    try:
        # Read bytes then decode
        raw = django_file.read()
        content = _decode(raw)

        transactions = _parse_content(content, filename, session, source, log)

        if not transactions:
            log.status = 'failed'
            log.error_message = (
                'No valid transactions found. Check that the file has the correct columns: '
                'date, reference, narration, debit/credit (or amount).'
            )
            log.save()
            return 0, log.error_message

        Transaction.objects.bulk_create(transactions, batch_size=500)
        log.rows_extracted = len(transactions)
        log.save()
        return len(transactions), ''

    except Exception as exc:
        log.status = 'failed'
        log.error_message = str(exc)
        log.save()
        return 0, str(exc)


def _decode(raw: bytes) -> str:
    for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def _parse_content(content, filename, session, source, log):
    """Detect format and parse rows."""
    fname = filename.lower()
    if fname.endswith('.csv') or fname.endswith('.txt'):
        return _parse_csv(content, session, source, log)
    # Default: try CSV anyway
    return _parse_csv(content, session, source, log)


def _parse_csv(content, session, source, log):
    # Auto-detect delimiter from first 2 KB
    sample = content[:2000]
    delimiter = max([',', '\t', '|', ';'], key=lambda d: sample.count(d))

    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    rows = []
    for row in reader:
        t = _parse_row(row, session, source, log)
        if t:
            rows.append(t)
    return rows


def _to_decimal(val) -> Decimal:
    if not val:
        return Decimal('0')
    cleaned = str(val).replace(',', '').replace(' ', '').strip()
    if not cleaned:
        return Decimal('0')
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal('0')


def _parse_date(val):
    if not val:
        return None
    val = str(val).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y',
                '%Y/%m/%d', '%d %b %Y', '%d-%b-%Y', '%d %B %Y',
                '%d/%m/%y', '%m/%d/%y'):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def _parse_row(row, session, source, log):
    try:
        k = {key.lower().strip().replace(' ', '_'): (v or '').strip()
             for key, v in row.items() if key}

        # Date
        date_val = (k.get('date') or k.get('transaction_date') or k.get('trans_date') or
                    k.get('txn_date') or k.get('posting_date') or k.get('value_date') or '')
        date_obj = _parse_date(date_val)
        if not date_obj:
            return None

        # Value date (optional)
        vd_val = k.get('value_date') or ''
        value_date = _parse_date(vd_val) if vd_val and vd_val != date_val else None

        # Amounts
        debit  = _to_decimal(k.get('debit')  or k.get('debit_amount')  or k.get('dr') or k.get('dr_amount') or '')
        credit = _to_decimal(k.get('credit') or k.get('credit_amount') or k.get('cr') or k.get('cr_amount') or '')
        amount = _to_decimal(k.get('amount') or k.get('transaction_amount') or '')

        if amount != 0 and debit == 0 and credit == 0:
            if amount < 0:
                debit = abs(amount)
            else:
                credit = amount

        if debit == 0 and credit == 0:
            return None  # Nothing to reconcile

        # Reference
        reference = (k.get('reference') or k.get('ref') or k.get('ref_no') or
                     k.get('reference_number') or k.get('cheque_no') or
                     k.get('check_no') or k.get('tran_id') or
                     k.get('transaction_id') or k.get('receipt_no') or '')[:200]

        # Narration
        narration = (k.get('narration') or k.get('description') or
                     k.get('particulars') or k.get('remarks') or
                     k.get('memo') or k.get('details') or '')

        # Currency
        currency = (k.get('currency') or k.get('ccy') or 'GHS')[:3].upper()
        if len(currency) != 3:
            currency = 'GHS'

        txn_type = (k.get('type') or k.get('transaction_type') or k.get('tran_type') or '')[:50]

        return Transaction(
            session=session,
            upload_log=log,
            source=source,
            transaction_date=date_obj,
            value_date=value_date,
            reference_number=reference,
            narration=narration,
            debit_amount=debit,
            credit_amount=credit,
            currency=currency,
            transaction_type=txn_type,
            status='unmatched',
        )
    except Exception:
        return None


# ─── Reconciliation Engine ────────────────────────────────────────────────────

def run_reconciliation(session):
    """
    Match bank vs ledger transactions using 4 rules in priority order.
    Resets prior match state first so re-runs are safe.
    Returns (matched_pairs, unmatched_bank_count, unmatched_ledger_count).
    """
    session.status = 'processing'
    session.save()

    # Reset previous run
    session.transactions.update(status='unmatched', matched_with=None, match_confidence=0)
    session.exceptions.all().delete()

    bank_txns   = list(session.transactions.filter(source='bank',                   status='unmatched'))
    ledger_txns = list(session.transactions.filter(source__in=['ledger', 'payment'], status='unmatched'))

    matched_bank_ids   = set()
    matched_ledger_ids = set()
    pairs = []  # (bank_txn, ledger_txn, confidence)

    def amt(t):
        return t.credit_amount if t.credit_amount > 0 else t.debit_amount

    # Rule 1 — Exact: same amount + same reference + same date
    for bt in bank_txns:
        if bt.id in matched_bank_ids:
            continue
        for lt in ledger_txns:
            if lt.id in matched_ledger_ids:
                continue
            if (amt(bt) == amt(lt)
                    and bt.reference_number and lt.reference_number
                    and bt.reference_number.strip().lower() == lt.reference_number.strip().lower()
                    and bt.transaction_date == lt.transaction_date):
                pairs.append((bt, lt, 100.0))
                matched_bank_ids.add(bt.id)
                matched_ledger_ids.add(lt.id)
                break

    # Rule 2 — Amount + date window (±3 days), pick closest
    for bt in bank_txns:
        if bt.id in matched_bank_ids:
            continue
        best_lt, best_diff = None, 999
        for lt in ledger_txns:
            if lt.id in matched_ledger_ids:
                continue
            if amt(bt) == amt(lt):
                diff = abs((bt.transaction_date - lt.transaction_date).days)
                if diff <= 3 and diff < best_diff:
                    best_lt, best_diff = lt, diff
        if best_lt:
            confidence = round(95 - best_diff * 5, 1)
            pairs.append((bt, best_lt, confidence))
            matched_bank_ids.add(bt.id)
            matched_ledger_ids.add(best_lt.id)

    # Rule 3 — Fuzzy reference (≥ 85%) + same amount
    for bt in bank_txns:
        if bt.id in matched_bank_ids or not bt.reference_number:
            continue
        best_lt, best_ratio = None, 0.0
        for lt in ledger_txns:
            if lt.id in matched_ledger_ids or not lt.reference_number:
                continue
            if amt(bt) == amt(lt):
                ratio = SequenceMatcher(
                    None,
                    bt.reference_number.strip().lower(),
                    lt.reference_number.strip().lower()
                ).ratio()
                if ratio >= 0.85 and ratio > best_ratio:
                    best_lt, best_ratio = lt, ratio
        if best_lt:
            pairs.append((bt, best_lt, round(best_ratio * 100, 1)))
            matched_bank_ids.add(bt.id)
            matched_ledger_ids.add(best_lt.id)

    # Rule 4 — Narration similarity (≥ 80%) + same amount
    for bt in bank_txns:
        if bt.id in matched_bank_ids or not bt.narration:
            continue
        best_lt, best_ratio = None, 0.0
        for lt in ledger_txns:
            if lt.id in matched_ledger_ids or not lt.narration:
                continue
            if amt(bt) == amt(lt):
                ratio = SequenceMatcher(
                    None,
                    bt.narration.strip().lower(),
                    lt.narration.strip().lower()
                ).ratio()
                if ratio >= 0.80 and ratio > best_ratio:
                    best_lt, best_ratio = lt, ratio
        if best_lt:
            pairs.append((bt, best_lt, round(best_ratio * 100, 1)))
            matched_bank_ids.add(bt.id)
            matched_ledger_ids.add(best_lt.id)

    # Persist matches
    for bt, lt, confidence in pairs:
        bt.status = 'matched'; bt.matched_with = lt; bt.match_confidence = confidence
        bt.save(update_fields=['status', 'matched_with', 'match_confidence'])
        lt.status = 'matched'; lt.matched_with = bt; lt.match_confidence = confidence
        lt.save(update_fields=['status', 'matched_with', 'match_confidence'])

    # Exceptions for unmatched
    for txn in session.transactions.filter(status='unmatched'):
        cat = 'missing_in_ledger' if txn.source == 'bank' else 'missing_in_bank'
        ExceptionModel.objects.get_or_create(
            session=session, transaction=txn,
            defaults={'category': cat, 'description': 'No match found after all reconciliation rules.'}
        )

    # Amount-difference detection (same ref, different amount)
    _detect_amount_differences(session)

    session.status = 'pending_review'
    session.save()

    ub = session.transactions.filter(source='bank',                    status='unmatched').count()
    ul = session.transactions.filter(source__in=['ledger', 'payment'], status='unmatched').count()
    return len(pairs), ub, ul


def _detect_amount_differences(session):
    unmatched_bank   = list(session.transactions.filter(source='bank', status='unmatched').exclude(reference_number=''))
    unmatched_ledger = list(session.transactions.filter(source__in=['ledger', 'payment'], status='unmatched').exclude(reference_number=''))

    ledger_by_ref = {}
    for lt in unmatched_ledger:
        ledger_by_ref.setdefault(lt.reference_number.strip().lower(), []).append(lt)

    for bt in unmatched_bank:
        key = bt.reference_number.strip().lower()
        for lt in ledger_by_ref.get(key, []):
            b_amt = bt.credit_amount if bt.credit_amount > 0 else bt.debit_amount
            l_amt = lt.credit_amount if lt.credit_amount > 0 else lt.debit_amount
            if b_amt != l_amt:
                ExceptionModel.objects.update_or_create(
                    session=session, transaction=bt,
                    defaults={
                        'category': 'amount_diff',
                        'description': (
                            f"Reference '{bt.reference_number}' exists in both sources "
                            f"but amounts differ — Bank: {b_amt}, Ledger: {l_amt}"
                        )
                    }
                )
