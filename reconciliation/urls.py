from django.urls import path
from . import views

app_name = 'reconciliation'

urlpatterns = [
    path('bank-accounts/', views.bank_account_list, name='bank_account_list'),
    path('bank-accounts/create/', views.bank_account_create, name='bank_account_create'),
    path('bank-accounts/<int:pk>/edit/', views.bank_account_edit, name='bank_account_edit'),
    path('sessions/', views.session_list, name='session_list'),
    path('sessions/create/', views.session_create, name='session_create'),
    path('sessions/<int:pk>/', views.session_detail, name='session_detail'),
    path('sessions/<int:session_pk>/upload/', views.upload_file, name='upload_file'),
    path('sessions/<int:session_pk>/run/', views.run_matching, name='run_matching'),
    path('sessions/<int:pk>/approve/', views.approve_session, name='approve_session'),
    path('exceptions/', views.exception_list, name='exception_list'),
    path('exceptions/<int:pk>/', views.exception_detail, name='exception_detail'),
    path('audit-log/', views.audit_log, name='audit_log'),
]
