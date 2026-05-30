from django import forms
from .models import BankAccount, ReconciliationSession, UploadedFile, Transaction, Exception as ExceptionModel


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['account_name', 'account_number', 'bank_name', 'currency', 'branch', 'status']
        widgets = {
            'account_name': forms.TextInput(attrs={'placeholder': 'e.g. Main Operating Account'}),
            'account_number': forms.TextInput(attrs={'placeholder': 'e.g. 1234567890'}),
            'bank_name': forms.TextInput(attrs={'placeholder': 'e.g. GCB Bank'}),
            'branch': forms.TextInput(attrs={'placeholder': 'e.g. Head Office'}),
        }


class ReconciliationSessionForm(forms.ModelForm):
    class Meta:
        model = ReconciliationSession
        fields = ['session_name', 'bank_account', 'period_start', 'period_end']
        widgets = {
            'session_name': forms.TextInput(attrs={'placeholder': 'e.g. January 2024 Reconciliation'}),
            'period_start': forms.DateInput(attrs={'type': 'date'}),
            'period_end': forms.DateInput(attrs={'type': 'date'}),
        }


class UploadFileForm(forms.ModelForm):
    class Meta:
        model = UploadedFile
        fields = ['file', 'category']


class ManualTransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['transaction_date', 'value_date', 'reference_number', 'narration',
                  'debit_amount', 'credit_amount', 'currency', 'transaction_type', 'source']
        widgets = {
            'transaction_date': forms.DateInput(attrs={'type': 'date'}),
            'value_date': forms.DateInput(attrs={'type': 'date'}),
            'narration': forms.Textarea(attrs={'rows': 2}),
        }


class ExceptionForm(forms.ModelForm):
    class Meta:
        model = ExceptionModel
        fields = ['status', 'resolution_notes', 'assigned_to']
        widgets = {
            'resolution_notes': forms.Textarea(attrs={'rows': 3}),
        }


class ApprovalForm(forms.Form):
    ACTION_CHOICES = [('approve', 'Approve'), ('reject', 'Reject'), ('rework', 'Request Rework')]
    action = forms.ChoiceField(choices=ACTION_CHOICES)
    comments = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
