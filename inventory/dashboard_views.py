
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.models import User
from datetime import datetime
from .models import ItemRequest, InventoryItem  # Ensure ItemRequest is defined in your models
from django.core.paginator import Paginator
from .utils import is_clerk, is_hod, is_faculty

def home(request):
    if is_clerk(request.user):
        return redirect('clerk_dashboard')
    elif is_faculty(request.user):
        return redirect('faculty_dashboard')
    elif is_hod(request.user):
        return redirect('hod_dashboard')
    else:
        return redirect('login')

@login_required
@user_passes_test(is_clerk)
def clerk_dashboard(request):
    # total_items = InventoryItem.objects.count()
    # low_stock_items = InventoryItem.objects.filter(quantity__lt=5).count()  # Adjust threshold
    # pending_requests = ItemRequest.objects.filter(user=request.user, status='pending').count()
    # issued_items = ItemRequest.objects.filter( status='issued').count()

    recent_requests = ItemRequest.objects.filter().order_by('-request_date')[:5]
    recent_approved_requests = ItemRequest.objects.filter(status = 'approved').order_by('-request_date')[:5]

    context = {
        # 'total_items': total_items,
        # 'low_stock': low_stock_items,
        # 'pending_requests': pending_requests,
        # 'issued_items': issued_items,
        'recent_requests': recent_requests,
        'recent_approved_requests':recent_approved_requests
    }
    return render(request, 'dashboard/clerk_dashboard.html', context)

from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
@user_passes_test(is_hod)
def hod_dashboard(request):
    total_requests = ItemRequest.objects.count()
    pending_requests = ItemRequest.objects.filter(status='pending').count()
    approved_requests = ItemRequest.objects.filter(status='approved').count()
    rejected_requests = ItemRequest.objects.filter(status='rejected').count()
    issued_requests = ItemRequest.objects.filter(status='issued').count()
    returned_requests = ItemRequest.objects.filter(status='returned').count()

    recent_requests = ItemRequest.objects.all().order_by('-request_date')[:5]

    context = {
        'total_requests': total_requests,
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'rejected_requests': rejected_requests,
        'issued_requests':issued_requests,
        'returned_requests':returned_requests,
        'recent_requests': recent_requests,
    }
    return render(request, 'dashboard/hod_dashboard.html', context)

@login_required
@user_passes_test(is_faculty)
def faculty_dashboard(request):
    items = InventoryItem.objects.all()
    my_requests = ItemRequest.objects.filter(user=request.user).order_by('-request_date')

    # Pagination for items
    items_paginator = Paginator(items, 100)  # Show 10 items per page
    items_page_number = request.GET.get('items_page')
    items_page = items_paginator.get_page(items_page_number)

    # Pagination for my_requests
    requests_paginator = Paginator(my_requests, 100)  # Show 10 requests per page
    requests_page_number = request.GET.get('requests_page')
    requests_page = requests_paginator.get_page(requests_page_number)

    return render(request, 'dashboard/faculty_dashboard.html', {
        'items': items_page,
        'my_requests': requests_page
    })

@login_required
@user_passes_test(is_clerk)
def issue_items(request):
    approved_requests = ItemRequest.objects.filter(status='approved').order_by('-request_date')
    return render(request, 'requests/issue_items.html', {'approved_requests': approved_requests})

@login_required
@user_passes_test(is_clerk)
@require_POST
def mark_as_issued(request, request_id):
    item_request = get_object_or_404(ItemRequest, id=request_id, status='approved')
    
    item = get_object_or_404(InventoryItem, id=item_request.item.id)
    request_quantity = item_request.quantity

    if item.quantity >= request_quantity:
        item.quantity -= request_quantity
        item.last_maintenance_date = datetime.now()
        item.save()
        item_request.status = 'issued'
        item_request.issued_date = datetime.now()
        item_request.save()
        messages.success(request, "Item marked as issued.")
    else:
        messages.error(request, "Not enough stock to issue the item.")

    return redirect('clerk_dashboard')  

@login_required
@user_passes_test(is_hod)
def manage_users(request):
    users = User.objects.all()
    return render(request, 'user/manage_users.html', {'users': users})
