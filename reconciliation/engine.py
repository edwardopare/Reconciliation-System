"""
Reconciliation Engine - Handles automatic transaction matching
"""
import csv
import io
import hashlib
from decimal import Decimal
from datetime import timedelta
from difflib import SequenceMatcher
from .models import Transaction, UploadedFile, Exception as ExceptionModel


def parse_and_extract(uploaded_file_obj):
    """Parse uploaded file and extract transactions."""
    try:
        file = uploaded_file_obj.file
        filename = uploaded_file_obj.original_filename.lower()
        session = uploaded_file_obj.session
        source_map = {
            'bank_statement': 'bank',
            'internal_ledger': 'ledger',
            'payment_gateway': 'payment',
        }
        source = source_map.get(uploaded_file_obj.category, 'bank')

        transactions = []
        file.seek(0)
        content = file.read().decode('utf-8', errors='replace')

        if filename.endswith('.csv') or filename.endswith('.txt'):
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                t = _parse_row(row, session, source, uploaded_file_obj)
                if t:
                    transactions.append(t)

        uploaded_file_obj.rows_extracted = len(transactions)
        uploaded_file_obj.status = 'processed'
        uploaded_file_obj.save()

        Transaction.objects.bulk_create(transactions)
        return len(transactions)

    except Exception as e:
        uploaded_file_obj.status = 'failed'
        uploaded_file_obj.error_message = str(e)
        uploaded_file_obj.save()
        return 0


def _parse_row(row, session, source, uploaded_file_obj):
    """Parse a CSV row into a Transaction."""
    try:
        keys = {k.lower().strip(): v for k, v in row.items()}
        date_val = keys.get('date') or keys.get('transaction_date') or keys.get('trans_date', '')
        if not date_val:
            return None
        from django.utils.dateparse import parse_date
        from datetime import datetime
        date_obj = None
        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y']:
            try:
                date_obj = datetime.strptime(date_val.strip(), fmt).date()
                break
            except:
                pass
        if not date_obj:
            return None

        debit = Decimal(str(keys.get('debit', '') or keys.get('debit_amount', '') or '0').replace(',', '') or '0')
        credit = Decimal(str(keys.get('credit', '') or keys.get('credit_amount', '') or '0').replace(',', '') or '0')
        amount = Decimal(str(keys.get('amount', '') or '0').replace(',', '') or '0')
        if amount > 0 and debit == 0 and credit == 0:
            credit = amount

        return Transaction(
            session=session,
            uploaded_file=uploaded_file_obj,
            source=source,
            transaction_date=date_obj,
            reference_number=str(keys.get('reference', '') or keys.get('ref', '') or keys.get('ref_no', '') or '')[:200],
            narration=str(keys.get('narration', '') or keys.get('description', '') or keys.get('particulars', '') or ''),
            debit_amount=debit,
            credit_amount=credit,
            currency=str(keys.get('currency', 'GHS') or 'GHS')[:3],
            transaction_type=str(keys.get('type', '') or keys.get('transaction_type', '') or '')[:50],
        )
    except Exception:
        return None


def run_reconciliation(session):
    """Run all matching rules for a session."""
    session.status = 'processing'
    session.save()

    bank_txns = list(session.transactions.filter(source='bank', status='unmatched'))
    ledger_txns = list(session.transactions.filter(source__in=['ledger', 'payment'], status='unmatched'))

    matched_pairs = []

    # Rule 1: Exact match (amount + reference + date)
    for bt in bank_txns[:]:
        for lt in ledger_txns[:]:
            if lt in [p[1] for p in matched_pairs]:
                continue
            if (bt.amount == lt.amount and
                bt.reference_number and lt.reference_number and
                bt.reference_number.lower() == lt.reference_number.lower() and
                bt.transaction_date == lt.transaction_date):
                matched_pairs.append((bt, lt, 100.0))
                break

    # Rule 2: Amount + Date (within 3 days)
    matched_ids = {t.id for pair in matched_pairs for t in [pair[0], pair[1]]}
    for bt in bank_txns:
        if bt.id in matched_ids:
            continue
        for lt in ledger_txns:
            if lt.id in matched_ids:
                continue
            if bt.amount == lt.amount:
                date_diff = abs((bt.transaction_date - lt.transaction_date).days)
                if date_diff <= 3:
                    matched_pairs.append((bt, lt, 85.0))
                    matched_ids.add(bt.id)
                    matched_ids.add(lt.id)
                    break

    # Rule 3: Reference similarity (fuzzy 90%)
    for bt in bank_txns:
        if bt.id in matched_ids:
            continue
        for lt in ledger_txns:
            if lt.id in matched_ids:
                continue
            if bt.reference_number and lt.reference_number:
                ratio = SequenceMatcher(None, bt.reference_number.lower(), lt.reference_number.lower()).ratio()
                if ratio >= 0.90 and bt.amount == lt.amount:
                    matched_pairs.append((bt, lt, round(ratio * 100, 1)))
                    matched_ids.add(bt.id)
                    matched_ids.add(lt.id)
                    break

    # Save matches
    for bt, lt, confidence in matched_pairs:
        bt.status = 'matched'
        bt.matched_with = lt
        bt.match_confidence = confidence
        bt.save()
        lt.status = 'matched'
        lt.matched_with = bt
        lt.match_confidence = confidence
        lt.save()

    # Create exceptions for unmatched
    for txn in session.transactions.filter(status='unmatched'):
        if txn.source == 'bank':
            cat = 'missing_in_ledger'
        else:
            cat = 'missing_in_bank'
        ExceptionModel.objects.get_or_create(
            session=session,
            transaction=txn,
            defaults={'category': cat}
        )

    session.status = 'pending_review'
    session.save()

    return len(matched_pairs)
