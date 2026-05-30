from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'System Administrator'),
        ('officer', 'Reconciliation Officer'),
        ('manager', 'Finance Manager'),
        ('auditor', 'Internal Auditor'),
        ('executive', 'Executive User'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='officer')
    phone = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=100, blank=True)
    is_locked = models.BooleanField(default=False)
    last_password_change = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    def can_approve(self):
        return self.role in ['manager', 'admin']

    def can_upload(self):
        return self.role in ['officer', 'admin']

    def is_read_only(self):
        return self.role in ['auditor', 'executive']
