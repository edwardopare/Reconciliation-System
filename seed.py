"""Seed demo data for BRMS"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'brms.settings')
sys.path.insert(0, '/home/claude')
django.setup()

from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from accounts.models import User
from reconciliation.models import BankAccount, ReconciliationSession, Transaction, Exception as ExceptionModel, AuditLog

print("Creating users...")
admin = User.objects.create_superuser('admin', 'admin@brms.gh', 'admin1234', first_name='System', last_name='Admin', role='admin')
officer = User.objects.create_user('j.mensah', 'j.mensah@brms.gh', 'pass1234', first_name='Joana', last_name='Mensah', role='officer', department='Finance')
manager = User.objects.create_user('k.boateng', 'k.boateng@brms.gh', 'pass1234', first_name='Kwame', last_name='Boateng', role='manager', department='Finance')
auditor = User.objects.create_user('a.asante', 'a.asante@brms.gh', 'pass1234', first_name='Ama', last_name='Asante', role='auditor', department='Internal Audit')
executive = User.objects.create_user('d.appiah', 'd.appiah@brms.gh', 'pass1234', first_name='David', last_name='Appiah', role='executive', department='Executive')
print(f"  Created {User.objects.count()} users")

print("Creating bank accounts...")
gcb = BankAccount.objects.create(account_name='Main Operating Account', account_number='1234567890', bank_name='GCB Bank', currency='GHS', branch='Head Office', created_by=admin)
ecobank = BankAccount.objects.create(account_name='Payroll Account', account_number='9876543210', bank_name='Ecobank Ghana', currency='GHS', branch='Airport City', created_by=admin)
stanbic = BankAccount.objects.create(account_name='USD Treasury Account', account_number='USD-001-2024', bank_name='Stanbic Bank', currency='USD', branch='Accra Central', created_by=admin)
print(f"  Created {BankAccount.objects.count()} bank accounts")

print("Creating reconciliation sessions...")
today = date.today()

# Session 1 - Approved
s1 = ReconciliationSession.objects.create(
    session_name='March 2024 GCB Reconciliation', bank_account=gcb,
    period_start=date(2024,3,1), period_end=date(2024,3,31),
    status='approved', created_by=officer, approved_by=manager,
    approval_date=timezone.now(), approval_comments='All transactions verified.'
)
for i in range(12):
    ref = f'TXN-GCB-{1000+i}'
    amt = Decimal(str((i+1)*500 + 250))
    t_bank = Transaction.objects.create(session=s1, source='bank', transaction_date=date(2024,3,i+1),
        reference_number=ref, narration=f'Payment to vendor {i+1}', credit_amount=amt, currency='GHS', status='matched')
    t_ledger = Transaction.objects.create(session=s1, source='ledger', transaction_date=date(2024,3,i+1),
        reference_number=ref, narration=f'Payment to vendor {i+1}', credit_amount=amt, currency='GHS', status='matched')
    t_bank.matched_with = t_ledger; t_bank.match_confidence = 100.0; t_bank.save()
    t_ledger.matched_with = t_bank; t_ledger.match_confidence = 100.0; t_ledger.save()

# Session 2 - Pending Review with exceptions
s2 = ReconciliationSession.objects.create(
    session_name='April 2024 GCB Reconciliation', bank_account=gcb,
    period_start=date(2024,4,1), period_end=date(2024,4,30),
    status='pending_review', created_by=officer
)
for i in range(8):
    ref = f'TXN-APR-{2000+i}'
    amt = Decimal(str((i+2)*1200))
    t_bank = Transaction.objects.create(session=s2, source='bank', transaction_date=date(2024,4,i+1),
        reference_number=ref, narration=f'Bank transaction {i+1}', credit_amount=amt, currency='GHS', status='matched')
    t_ledger = Transaction.objects.create(session=s2, source='ledger', transaction_date=date(2024,4,i+1),
        reference_number=ref, narration=f'Ledger entry {i+1}', credit_amount=amt, currency='GHS', status='matched')
    t_bank.matched_with = t_ledger; t_bank.match_confidence = 95.0; t_bank.save()
    t_ledger.matched_with = t_bank; t_ledger.match_confidence = 95.0; t_ledger.save()
# Add some unmatched with exceptions
for i in range(3):
    t_unmatched = Transaction.objects.create(session=s2, source='bank', transaction_date=date(2024,4,15+i),
        reference_number=f'UNMATCHED-{i+1}', narration=f'Unidentified debit {i+1}',
        debit_amount=Decimal(str((i+1)*800)), currency='GHS', status='unmatched')
    ExceptionModel.objects.create(session=s2, transaction=t_unmatched, category='missing_in_ledger', status='open',
        description='Transaction found in bank but not in ledger.')

# Session 3 - Draft
s3 = ReconciliationSession.objects.create(
    session_name='May 2024 GCB Reconciliation', bank_account=gcb,
    period_start=date(2024,5,1), period_end=date(2024,5,31),
    status='draft', created_by=officer
)

# Session 4 - Ecobank approved
s4 = ReconciliationSession.objects.create(
    session_name='Q1 2024 Payroll Reconciliation', bank_account=ecobank,
    period_start=date(2024,1,1), period_end=date(2024,3,31),
    status='approved', created_by=officer, approved_by=manager, approval_date=timezone.now()
)
for i in range(6):
    ref = f'PYRL-{3000+i}'
    amt = Decimal(str(5000 + i*200))
    t_b = Transaction.objects.create(session=s4, source='bank', transaction_date=date(2024,1, min(i*5+1, 28)),
        reference_number=ref, narration=f'Payroll run {i+1}', debit_amount=amt, currency='GHS', status='matched')
    t_l = Transaction.objects.create(session=s4, source='ledger', transaction_date=date(2024,1, min(i*5+1, 28)),
        reference_number=ref, narration=f'Payroll run {i+1}', debit_amount=amt, currency='GHS', status='matched')
    t_b.matched_with = t_l; t_b.match_confidence = 100.0; t_b.save()
    t_l.matched_with = t_b; t_l.match_confidence = 100.0; t_l.save()

# Add some audit logs
for action, entity in [('LOGIN','User'),('CREATE_SESSION','ReconciliationSession'),('UPLOAD_FILE','UploadedFile'),
                        ('RUN_MATCHING','ReconciliationSession'),('SESSION_APPROVE','ReconciliationSession')]:
    AuditLog.objects.create(user=officer, action=action, entity=entity, entity_id='1',
        new_value=f'Demo {action}', ip_address='127.0.0.1', device_info='Demo Browser')

print(f"  Created {ReconciliationSession.objects.count()} sessions")
print(f"  Created {Transaction.objects.count()} transactions")
print(f"  Created {ExceptionModel.objects.count()} exceptions")
print(f"  Created {AuditLog.objects.count()} audit logs")
print("\n✓ Seed complete!")
print("\nDemo credentials:")
print("  admin    / admin1234  (System Administrator)")
print("  j.mensah / pass1234   (Reconciliation Officer)")
print("  k.boateng/ pass1234   (Finance Manager)")
print("  a.asante / pass1234   (Internal Auditor)")
