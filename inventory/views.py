from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, logout, authenticate
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib.auth.models import Group
from .utils import is_clerk, is_faculty, is_hod, forecast_usage_from_excel
from .models import ItemRequest, InventoryItem
from .forms import InventoryItemForm
from notifications.utils import notify_user
from django.contrib.auth.models import User
import datetime
import os
from django.core.mail import send_mail

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
def logout_page(request):
    logout(request)
    return redirect('login')

def login_page(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home') 
        else:
            messages.error(request, 'Invalid Credentials')
    return render(request, 'user/login.html')

@login_required
def view_requests(request):
    requests = ItemRequest.objects.all().order_by('-request_date')
    return render(request, 'requests/view_requests.html', {'requests': requests})

@user_passes_test(is_hod or is_clerk)
def manage_requests(request):
    requests = ItemRequest.objects.all().order_by('-request_date')
    return render(request, 'inventory/manage_requests.html', {'requests': requests})

@user_passes_test(is_hod)
@require_POST
def process_request(request, request_id):
    item_request = get_object_or_404(ItemRequest, id=request_id)
    action = request.POST.get('action')

    if item_request.status != 'pending':
        messages.warning(request, "This request has already been processed.")
        return redirect('hod_dashboard')

    if action == 'approve':
        item = item_request.item
        if item.quantity >= item_request.quantity:
            item.quantity -= item_request.quantity
            item.save()

            item_request.status = 'approved'
            item_request.processed_by = request.user
            item_request.decision_date = datetime.now()
            item_request.save()
            notify_user(item_request.user, f"Your request for {item.name} has been approved by {request.user}.")
            clerk_group = Group.objects.get(name='Clerk')
            for clerk in clerk_group.user_set.all():
                notify_user(clerk, f" {item_request.user}'s request for {item.name} has been approved by {request.user}.")
            messages.success(request, "Request approved and inventory updated.")
        else:
            messages.error(request, "Not enough stock to approve this request.")
            return redirect('hod_dashboard')

    elif action == 'reject':
        item_request.status = 'rejected'
        item_request.processed_by = request.user
        item_request.save()
        notify_user(item_request.user, f"Your request for {item.item.name} has been rejected.")
        messages.info(request, "Request has been rejected.")

    else:
        messages.error(request, "Invalid action.")
    
    return redirect('hod_dashboard')


@login_required
def request_history(request):
    if is_faculty(request.user):
        requests = ItemRequest.objects.filter(user=request.user).order_by('-request_date')
    else: 
        requests = ItemRequest.objects.all().order_by('-request_date')
    return render(request, 'requests/request_history.html', {'requests': requests})


@login_required
@user_passes_test(is_clerk)
def clerk_dashboard(request):
    total_items = InventoryItem.objects.count()
    low_stock_items = InventoryItem.objects.filter(quantity__lt=5).count()  # Adjust threshold
    pending_requests = ItemRequest.objects.filter(user=request.user, status='pending').count()
    issued_items = ItemRequest.objects.filter(user=request.user, status='issued').count()

    recent_requests = ItemRequest.objects.filter().order_by('-request_date')[:5]

    context = {
        'total_items': total_items,
        'low_stock': low_stock_items,
        'pending_requests': pending_requests,
        'issued_items': issued_items,
        'recent_requests': recent_requests,
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

    recent_requests = ItemRequest.objects.all().order_by('-request_date')[:5]

    context = {
        'total_requests': total_requests,
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'rejected_requests': rejected_requests,
        'recent_requests': recent_requests,
    }
    return render(request, 'dashboard/hod_dashboard.html', context)

@login_required
@user_passes_test(is_faculty)
def faculty_dashboard(request):
    items = InventoryItem.objects.all()
    my_requests = ItemRequest.objects.filter(user=request.user).order_by('-request_date')
    return render(request, 'dashboard/faculty_dashboard.html', {
        'items': items,
        'my_requests': my_requests
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
    item_request = get_object_or_404(ItemRequest, id=request_id, status='Approved')

    item_request.status = 'Issued'
    item_request.save()
    messages.success(request, "Item marked as issued.")
    return redirect('issue_items')  

@login_required
def show_all_items(request):
    items = InventoryItem.objects.all()

    in_stock_items = items.filter(quantity__gte=5).count()   # Only items with good stock
    low_stock_items = items.filter(quantity__gt=0, quantity__lt=10).count()
    out_of_stock_items = items.filter(quantity=0).count()

    stock_info = {
        'in_stock': in_stock_items,
        'low_stock': low_stock_items,
        'out_stock': out_of_stock_items,
    }
    categories = InventoryItem.CATEGORY_CHOICES
    return render(request, 'inventory/show_all_items.html', {
        'items': items,
        'stock_info': stock_info,
        'categories': categories,
    })

@login_required
@require_POST
@user_passes_test(is_clerk)
def delete_item(request, pk):
    try:
        item = InventoryItem.objects.get(pk=pk)
        item.delete()
        return JsonResponse({'success': True})
    except InventoryItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item not found'})

@login_required
@user_passes_test(is_clerk)
def add_item(request):
    if request.method == 'POST':
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Item added successfully.")
            return redirect('add_item')
    else:
        form = InventoryItemForm()
    return render(request, 'inventory/add_item.html', {'form': form})

@login_required
@user_passes_test(is_clerk)
def edit_item(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)
    if request.method == 'POST':
        form = InventoryItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, "Item updated successfully.")
            return redirect('inventory_items')
    else:
        form = InventoryItemForm(instance=item)
    return render(request, 'inventory/edit_item.html', {'form': form, 'item': item})




@login_required
def request_item_page(request):
    items = InventoryItem.objects.filter(quantity__gt=0)
    return render(request, 'requests/request_item.html', {'items': items})

@login_required
def submit_item_request(request):
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        quantity = request.POST.get('quantity')
        reason = request.POST.get('reason')
        item = get_object_or_404(InventoryItem, id=item_id)

        ItemRequest.objects.create(
            user=request.user,
            item=item,
            quantity=quantity,
            reason=reason,
            status='pending'
        )
        hod_group = Group.objects.get(name='HOD')
        for hod in hod_group.user_set.all():
            notify_user(hod, f"{request.user.username} requested {item.name} of quantity {quantity}.")
        messages.success(request, 'Request submitted successfully.')
        return redirect('home')
    return HttpResponseBadRequest("Invalid request.")

@login_required
def category_list(request):
    categories = InventoryItem.CATEGORY_CHOICES
    if request.method == 'GET':
        category = request.GET.get('category')
        if category == 'all':
            items = InventoryItem.objects.all()
        else:
            items = InventoryItem.objects.filter(category=category)
    else:
        items = InventoryItem.objects.all()
    return render(request, 'inventory/show_all_items.html', {'categories': categories, 'items': items})

from django.shortcuts import render
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from datetime import datetime
import os

def inventory_forecast_view(request):
    forecast_results = None
    forecast_year = [ datetime.now().year + 1, datetime.now().year + 2 ]  # Default to next year
    year = datetime.now().year + 1  
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        year = request.POST.get('forecast_year')
        if uploaded_file.name.endswith('.xlsx'):
            fs = FileSystemStorage()
            filename = fs.save(uploaded_file.name, uploaded_file)
            file_path = fs.path(filename)

            try:
                
                forecast_results = forecast_usage_from_excel(file_path, int(year))

            except Exception as e:
                messages.error(request, f"Error processing file: {e}")
            finally:
                os.remove(file_path)
        else:
            messages.error(request, "Please upload a .xlsx file only.")

    return render(request, 'forecast/forecast_page.html', {
        'forecast_data': forecast_results,
        'forecast_year': forecast_year,
        'selected_year': year
    })


@login_required
@user_passes_test(is_clerk or is_hod)
def predict_usage(request, year):
    forecast_data = {}
    try:
        year = int(year)
    except ValueError:
        return JsonResponse({'error': 'Invalid year format'}, status=400)
    forecast_year = year 

    excel_path = os.path.join('media', 'stationery_usage.xlsx') 
    try:
        forecast_data = forecast_usage_from_excel(excel_path, forecast_year)
    except Exception as e:
        forecast_data = {'error': str(e)}

    return render(request, 'predict_usage.html', {
        'forecast_data': forecast_data,
        'forecast_year': forecast_year
    })

@login_required
@user_passes_test(is_hod)
def manage_users(request):
    users = User.objects.all()
    return render(request, 'user/manage_users.html', {'users': users})


from django.contrib.auth.models import User, Group
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.contrib import messages
from django.template.loader import render_to_string
from .utils import is_hod

@login_required
@user_passes_test(is_hod)
def create_user(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        group_name = request.POST.get('group')
        email = request.POST.get('email')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists. Please choose a different one.")
            return redirect('create_user')

        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Invalid email address provided.")
            return redirect('create_user')

        try:
            # Create user
            user = User.objects.create_user(username=username, password=password, email=email)

            # Assign group
            try:
                group = Group.objects.get(name=group_name)
                user.groups.add(group)
            except Group.DoesNotExist:
                user.delete()  # rollback
                messages.error(request, f"Group '{group_name}' does not exist.")
                return redirect('create_user')

            # Send welcome email
            subject = "Your Inventory System Account"
            message = render_to_string('emails/account_created_email.txt', {
                'username': username,
                'password': password,
            })

            send_mail(
                subject,
                message,
                'aniketwakte42@gmail.com',
                [email],
                fail_silently=False
            )

            messages.success(request, f"User {username} created successfully and notified by email.")
            return redirect('home')

        except Exception as e:
            messages.error(request, f"Error creating user: {e}")
            return redirect('create_user')

    return render(request, 'user/create_user.html')
