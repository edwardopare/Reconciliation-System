from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from reconciliation.models import ReconciliationSession, Transaction, Exception as ExceptionModel, AuditLog
from django.utils import timezone
from datetime import timedelta


@login_required
def home(request):
    today = timezone.now().date()
    thirty_days_ago = today - timedelta(days=30)

    total_sessions = ReconciliationSession.objects.count()
    pending_approvals = ReconciliationSession.objects.filter(status='pending_review').count()
    open_exceptions = ExceptionModel.objects.filter(status='open').count()

    all_sessions = ReconciliationSession.objects.all()
    total_txns = Transaction.objects.count()
    matched_txns = Transaction.objects.filter(status__in=['matched', 'manually_matched']).count()
    match_rate = round((matched_txns / total_txns * 100), 1) if total_txns > 0 else 0

    recent_sessions = ReconciliationSession.objects.select_related('bank_account', 'created_by').order_by('-created_at')[:8]
    recent_exceptions = ExceptionModel.objects.select_related('transaction', 'session').filter(status='open').order_by('-created_at')[:5]

    # Monthly trend (last 6 months)
    trend_data = []
    for i in range(5, -1, -1):
        d = today.replace(day=1) - timedelta(days=i * 28)
        month_sessions = ReconciliationSession.objects.filter(
            created_at__year=d.year, created_at__month=d.month
        ).count()
        trend_data.append({'month': d.strftime('%b %Y'), 'count': month_sessions})

    return render(request, 'dashboard/home.html', {
        'total_sessions': total_sessions,
        'pending_approvals': pending_approvals,
        'open_exceptions': open_exceptions,
        'match_rate': match_rate,
        'recent_sessions': recent_sessions,
        'recent_exceptions': recent_exceptions,
        'trend_data': trend_data,
    })
