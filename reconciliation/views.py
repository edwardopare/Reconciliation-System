from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Q, Count
from .models import BankAccount, ReconciliationSession, UploadedFile, Transaction, Exception as ExceptionModel, AuditLog
from .forms import BankAccountForm, ReconciliationSessionForm, UploadFileForm, ExceptionForm, ApprovalForm
from .engine import parse_and_extract, run_reconciliation


def log_action(request, action, entity, entity_id='', old='', new=''):
    ip = request.META.get('REMOTE_ADDR')
    ua = request.META.get('HTTP_USER_AGENT', '')[:500]
    AuditLog.objects.create(
        user=request.user, action=action, entity=entity,
        entity_id=str(entity_id), old_value=old, new_value=new,
        ip_address=ip, device_info=ua
    )


# ─── Bank Accounts ────────────────────────────────────────────────────────────
@login_required
def bank_account_list(request):
    accounts = BankAccount.objects.all().order_by('bank_name')
    return render(request, 'reconciliation/bank_account_list.html', {'accounts': accounts})


@login_required
def bank_account_create(request):
    if request.user.role not in ['admin']:
        messages.error(request, 'Access denied.')
        return redirect('reconciliation:bank_account_list')
    form = BankAccountForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        acc = form.save(commit=False)
        acc.created_by = request.user
        acc.save()
        log_action(request, 'CREATE_BANK_ACCOUNT', 'BankAccount', acc.id, new=acc.account_name)
        messages.success(request, 'Bank account created.')
        return redirect('reconciliation:bank_account_list')
    return render(request, 'reconciliation/bank_account_form.html', {'form': form, 'title': 'Add Bank Account'})


@login_required
def bank_account_edit(request, pk):
    if request.user.role not in ['admin']:
        messages.error(request, 'Access denied.')
        return redirect('reconciliation:bank_account_list')
    acc = get_object_or_404(BankAccount, pk=pk)
    form = BankAccountForm(request.POST or None, instance=acc)
    if request.method == 'POST' and form.is_valid():
        form.save()
        log_action(request, 'EDIT_BANK_ACCOUNT', 'BankAccount', acc.id)
        messages.success(request, 'Bank account updated.')
        return redirect('reconciliation:bank_account_list')
    return render(request, 'reconciliation/bank_account_form.html', {'form': form, 'title': 'Edit Bank Account', 'obj': acc})


# ─── Sessions ─────────────────────────────────────────────────────────────────
@login_required
def session_list(request):
    qs = ReconciliationSession.objects.select_related('bank_account', 'created_by').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(Q(session_name__icontains=search) | Q(session_id__icontains=search))
    paginator = Paginator(qs, 15)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'reconciliation/session_list.html', {
        'page_obj': page, 'status_filter': status_filter, 'search': search,
        'status_choices': ReconciliationSession.STATUS_CHOICES
    })


@login_required
def session_create(request):
    if request.user.is_read_only():
        messages.error(request, 'Access denied.')
        return redirect('reconciliation:session_list')
    form = ReconciliationSessionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        sess = form.save(commit=False)
        sess.created_by = request.user
        sess.save()
        log_action(request, 'CREATE_SESSION', 'ReconciliationSession', sess.id, new=sess.session_name)
        messages.success(request, f'Session {sess.session_id} created.')
        return redirect('reconciliation:session_detail', pk=sess.pk)
    return render(request, 'reconciliation/session_form.html', {'form': form, 'title': 'New Reconciliation Session'})


@login_required
def session_detail(request, pk):
    session = get_object_or_404(ReconciliationSession, pk=pk)
    transactions = session.transactions.all().order_by('-transaction_date')
    exceptions = session.exceptions.select_related('transaction').order_by('-created_at')
    files = session.uploaded_files.all()
    upload_form = UploadFileForm()

    # Stats
    total = transactions.count()
    matched = transactions.filter(status__in=['matched', 'manually_matched']).count()
    unmatched = transactions.filter(status='unmatched').count()
    ex_count = exceptions.filter(status='open').count()

    return render(request, 'reconciliation/session_detail.html', {
        'session': session,
        'transactions': transactions[:50],
        'exceptions': exceptions[:20],
        'files': files,
        'upload_form': upload_form,
        'total': total,
        'matched': matched,
        'unmatched': unmatched,
        'ex_count': ex_count,
        'match_rate': round((matched / total * 100), 1) if total > 0 else 0,
    })


@login_required
def upload_file(request, session_pk):
    session = get_object_or_404(ReconciliationSession, pk=session_pk)
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            uf = form.save(commit=False)
            uf.session = session
            uf.original_filename = request.FILES['file'].name
            uf.uploaded_by = request.user
            uf.save()
            rows = parse_and_extract(uf)
            log_action(request, 'UPLOAD_FILE', 'UploadedFile', uf.id, new=uf.original_filename)
            messages.success(request, f'File uploaded. {rows} transactions extracted.')
        else:
            messages.error(request, 'Invalid file upload.')
    return redirect('reconciliation:session_detail', pk=session_pk)


@login_required
def run_matching(request, session_pk):
    session = get_object_or_404(ReconciliationSession, pk=session_pk)
    if request.user.is_read_only():
        messages.error(request, 'Access denied.')
        return redirect('reconciliation:session_detail', pk=session_pk)
    count = run_reconciliation(session)
    log_action(request, 'RUN_MATCHING', 'ReconciliationSession', session.id, new=f'{count} pairs matched')
    messages.success(request, f'Reconciliation complete. {count} pairs matched.')
    return redirect('reconciliation:session_detail', pk=session_pk)


@login_required
def approve_session(request, pk):
    session = get_object_or_404(ReconciliationSession, pk=pk)
    if not request.user.can_approve():
        messages.error(request, 'You do not have permission to approve sessions.')
        return redirect('reconciliation:session_detail', pk=pk)
    form = ApprovalForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        action = form.cleaned_data['action']
        comments = form.cleaned_data.get('comments', '')
        if action == 'approve':
            session.status = 'approved'
            session.approved_by = request.user
            session.approval_date = timezone.now()
        elif action == 'reject':
            session.status = 'rejected'
        elif action == 'rework':
            session.status = 'draft'
        session.approval_comments = comments
        session.save()
        log_action(request, f'SESSION_{action.upper()}', 'ReconciliationSession', session.id, new=comments)
        messages.success(request, f'Session {action}d successfully.')
        return redirect('reconciliation:session_detail', pk=pk)
    return render(request, 'reconciliation/approve_session.html', {'session': session, 'form': form})


@login_required
def exception_list(request):
    qs = ExceptionModel.objects.select_related('transaction', 'session').order_by('-created_at')
    category = request.GET.get('category', '')
    status = request.GET.get('status', '')
    if category:
        qs = qs.filter(category=category)
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'reconciliation/exception_list.html', {
        'page_obj': page,
        'category': category,
        'status': status,
        'categories': ExceptionModel.CATEGORY_CHOICES,
        'statuses': ExceptionModel.STATUS_CHOICES,
    })


@login_required
def exception_detail(request, pk):
    exc = get_object_or_404(ExceptionModel, pk=pk)
    form = ExceptionForm(request.POST or None, instance=exc)
    if request.method == 'POST' and form.is_valid():
        form.save()
        log_action(request, 'UPDATE_EXCEPTION', 'Exception', exc.id)
        messages.success(request, 'Exception updated.')
        return redirect('reconciliation:exception_list')
    return render(request, 'reconciliation/exception_detail.html', {'exc': exc, 'form': form})


@login_required
def audit_log(request):
    qs = AuditLog.objects.select_related('user').order_by('-timestamp')
    search = request.GET.get('q', '')
    if search:
        qs = qs.filter(Q(action__icontains=search) | Q(entity__icontains=search))
    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'reconciliation/audit_log.html', {'page_obj': page, 'search': search})
