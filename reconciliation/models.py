from django.db import models
from django.conf import settings
import uuid


class BankAccount(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive'), ('frozen', 'Frozen')]
    CURRENCY_CHOICES = [('GHS', 'Ghana Cedis'), ('USD', 'US Dollar'), ('EUR', 'Euro'), ('GBP', 'British Pound')]

    account_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50, unique=True)
    bank_name = models.CharField(max_length=200)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='GHS')
    branch = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.account_name} - {self.account_number}"


class ReconciliationSession(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('processing', 'Processing'),
        ('pending_review', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('closed', 'Closed'),
    ]

    session_id = models.CharField(max_length=20, unique=True, editable=False)
    session_name = models.CharField(max_length=200)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='sessions_created')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions_approved')
    approval_date = models.DateTimeField(null=True, blank=True)
    approval_comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.session_id:
            count = ReconciliationSession.objects.count() + 1
            self.session_id = f"REC-{count:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.session_id} - {self.session_name}"

    @property
    def match_rate(self):
        total = self.transactions.count()
        if total == 0:
            return 0
        matched = self.transactions.filter(status='matched').count()
        return round((matched / total) * 100, 1)


class UploadedFile(models.Model):
    CATEGORY_CHOICES = [
        ('bank_statement', 'Bank Statement'),
        ('internal_ledger', 'Internal Ledger'),
        ('payment_gateway', 'Payment Gateway File'),
    ]
    STATUS_CHOICES = [('pending', 'Pending'), ('processing', 'Processing'), ('processed', 'Processed'), ('failed', 'Failed')]

    session = models.ForeignKey(ReconciliationSession, on_delete=models.CASCADE, related_name='uploaded_files')
    file = models.FileField(upload_to='uploads/')
    original_filename = models.CharField(max_length=255)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    checksum = models.CharField(max_length=64, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    rows_extracted = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)

    def __str__(self):
        return f"{self.original_filename} ({self.category})"


class Transaction(models.Model):
    SOURCE_CHOICES = [
        ('bank', 'Bank Statement'),
        ('ledger', 'Internal Ledger'),
        ('payment', 'Payment Gateway'),
    ]
    STATUS_CHOICES = [
        ('unmatched', 'Unmatched'),
        ('matched', 'Matched'),
        ('manually_matched', 'Manually Matched'),
        ('exception', 'Exception'),
        ('ignored', 'Ignored'),
    ]

    session = models.ForeignKey(ReconciliationSession, on_delete=models.CASCADE, related_name='transactions')
    uploaded_file = models.ForeignKey(UploadedFile, on_delete=models.SET_NULL, null=True, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    transaction_date = models.DateField()
    value_date = models.DateField(null=True, blank=True)
    reference_number = models.CharField(max_length=200, blank=True)
    narration = models.TextField(blank=True)
    debit_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    credit_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='GHS')
    transaction_type = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unmatched')
    matched_with = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='matched_by')
    match_confidence = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.reference_number or 'N/A'} - {self.transaction_date}"

    @property
    def amount(self):
        return self.credit_amount if self.credit_amount > 0 else self.debit_amount


class Exception(models.Model):
    CATEGORY_CHOICES = [
        ('missing_in_bank', 'Missing in Bank'),
        ('missing_in_ledger', 'Missing in Ledger'),
        ('duplicate', 'Duplicate Transaction'),
        ('amount_diff', 'Amount Difference'),
        ('date_diff', 'Date Difference'),
        ('reference_diff', 'Reference Difference'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved'),
        ('escalated', 'Escalated'),
        ('ignored', 'Ignored'),
    ]

    session = models.ForeignKey(ReconciliationSession, on_delete=models.CASCADE, related_name='exceptions')
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.category} - {self.transaction}"


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)
    entity = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=50, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_info = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} by {self.user} at {self.timestamp}"
