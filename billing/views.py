from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from dental_office.roles import staff_required
from patients.models import Patient
from appointments.models import Appointment
from .models import Invoice, Payment
from .forms import InvoiceForm, PaymentForm


@staff_required
def invoice_list(request):
    status = request.GET.get('status', '')
    invoices = Invoice.objects.select_related('patient', 'appointment')
    if status:
        invoices = invoices.filter(status=status)
    return render(request, 'billing/invoice_list.html', {
        'invoices': invoices,
        'status_filter': status,
    })


@staff_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    payment_form = PaymentForm()
    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'payment_form': payment_form,
    })


@staff_required
def invoice_add(request):
    initial = {}
    appt_pk = request.GET.get('appointment')
    if appt_pk:
        try:
            appt = Appointment.objects.get(pk=appt_pk)
            initial['appointment'] = appt
            initial['patient'] = appt.patient
        except Appointment.DoesNotExist:
            pass

    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save()
            return redirect('invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm(initial=initial)
    return render(request, 'billing/invoice_form.html', {'form': form, 'title': 'New Invoice'})


@staff_required
def invoice_edit(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        form = InvoiceForm(request.POST, instance=invoice)
        if form.is_valid():
            form.save()
            return redirect('invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm(instance=invoice)
    return render(request, 'billing/invoice_form.html', {'form': form, 'title': 'Edit Invoice', 'invoice': invoice})


@staff_required
def payment_add(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.invoice = invoice
            payment.save()
            if invoice.balance_due() <= 0:
                invoice.status = 'paid'
            elif invoice.amount_paid() > 0:
                invoice.status = 'partial'
            invoice.save()
            return redirect('invoice_detail', pk=invoice_pk)
    return redirect('invoice_detail', pk=invoice_pk)
