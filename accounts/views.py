from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from .models import User
from .forms import LoginForm, UserCreateForm, UserEditForm
from reconciliation.models import AuditLog


def log_action(request, action, entity, entity_id='', old='', new=''):
    ip = request.META.get('REMOTE_ADDR')
    ua = request.META.get('HTTP_USER_AGENT', '')[:500]
    AuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action, entity=entity, entity_id=str(entity_id),
        old_value=old, new_value=new, ip_address=ip, device_info=ua
    )


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:home')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        if user.is_locked:
            messages.error(request, 'Your account is locked. Contact an administrator.')
            return redirect('accounts:login')
        login(request, user)
        log_action(request, 'LOGIN', 'User', user.id)
        messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
        return redirect('dashboard:home')
    return render(request, 'accounts/login.html', {'form': form})


@login_required
def logout_view(request):
    log_action(request, 'LOGOUT', 'User', request.user.id)
    logout(request)
    return redirect('accounts:login')


@login_required
def user_list(request):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    users = User.objects.all().order_by('-created_at')
    paginator = Paginator(users, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'accounts/user_list.html', {'page_obj': page})


@login_required
def user_create(request):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    form = UserCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        log_action(request, 'CREATE_USER', 'User', user.id, new=user.username)
        messages.success(request, f'User {user.username} created successfully.')
        return redirect('accounts:user_list')
    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Create User'})


@login_required
def user_edit(request, pk):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    user = get_object_or_404(User, pk=pk)
    form = UserEditForm(request.POST or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        log_action(request, 'EDIT_USER', 'User', user.id, new=str(form.cleaned_data))
        messages.success(request, 'User updated successfully.')
        return redirect('accounts:user_list')
    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Edit User', 'edit_user': user})


@login_required
def user_toggle_lock(request, pk):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    user = get_object_or_404(User, pk=pk)
    user.is_locked = not user.is_locked
    user.save()
    action = 'LOCK_USER' if user.is_locked else 'UNLOCK_USER'
    log_action(request, action, 'User', user.id)
    messages.success(request, f'User {"locked" if user.is_locked else "unlocked"}.')
    return redirect('accounts:user_list')
