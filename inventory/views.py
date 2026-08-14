from django.db import transaction
from django.shortcuts import render, get_object_or_404, redirect

from dental_office.roles import staff_required
from .models import SupplyItem
from .forms import SupplyItemForm


@staff_required
def supply_list(request):
    items = SupplyItem.objects.all()
    low_stock = [i for i in items if i.is_low_stock()]
    return render(request, 'inventory/supply_list.html', {
        'items': items,
        'low_stock_count': len(low_stock),
    })


@staff_required
def supply_add(request):
    if request.method == 'POST':
        form = SupplyItemForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('supply_list')
    else:
        form = SupplyItemForm()
    return render(request, 'inventory/supply_form.html', {'form': form, 'title': 'Add Supply Item'})


@staff_required
def supply_edit(request, pk):
    item = get_object_or_404(SupplyItem, pk=pk)
    if request.method == 'POST':
        form = SupplyItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            return redirect('supply_list')
    else:
        form = SupplyItemForm(instance=item)
    return render(request, 'inventory/supply_form.html', {'form': form, 'title': 'Edit Supply Item', 'item': item})


@staff_required
def supply_adjust(request, pk):
    if request.method == 'POST':
        try:
            delta = int(request.POST.get('delta') or 0)
        except ValueError:
            delta = 0
        with transaction.atomic():
            item = get_object_or_404(SupplyItem.objects.select_for_update(), pk=pk)
            item.quantity = max(0, item.quantity + delta)
            item.save()
    return redirect('supply_list')
