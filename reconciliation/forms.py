from django import forms
from .models import BankAccount, ReconciliationSession, Exception as ExceptionModel
from accounts.models import User


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['account_name', 'account_number', 'bank_name', 'currency', 'branch', 'status']


class ReconciliationSessionForm(forms.ModelForm):
    class Meta:
        model = ReconciliationSession
        fields = ['session_name', 'bank_account', 'period_start', 'period_end']
        widgets = {
            'period_start': forms.DateInput(attrs={'type': 'date'}),
            'period_end':   forms.DateInput(attrs={'type': 'date'}),
        }


class FileUploadForm(forms.Form):
    """No model — just receives the file in memory."""
    CATEGORY_CHOICES = [
        ('bank_statement', 'Bank Statement'),
        ('internal_ledger', 'Internal Ledger'),
        ('payment_gateway', 'Payment Gateway File'),
    ]
    category = forms.ChoiceField(choices=CATEGORY_CHOICES)
    file = forms.FileField(
        help_text='CSV or TXT file only. File is processed immediately and not stored.',
        widget=forms.FileInput(attrs={'accept': '.csv,.txt'})
    )

    def clean_file(self):
        f = self.cleaned_data['file']
        name = f.name.lower()
        if not (name.endswith('.csv') or name.endswith('.txt')):
            raise forms.ValidationError('Only CSV and TXT files are supported.')
        if f.size > 10 * 1024 * 1024:  # 10 MB cap
            raise forms.ValidationError('File too large. Maximum size is 10 MB.')
        return f


class ExceptionForm(forms.ModelForm):
    class Meta:
        model = ExceptionModel
        fields = ['status', 'resolution_notes', 'assigned_to']
        widgets = {'resolution_notes': forms.Textarea(attrs={'rows': 3})}


class ApprovalForm(forms.Form):
    ACTION_CHOICES = [('approve', 'Approve'), ('reject', 'Reject'), ('rework', 'Request Rework')]
    action   = forms.ChoiceField(choices=ACTION_CHOICES)
    comments = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
