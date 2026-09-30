import mimetypes
import re

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from auditlog.signals import accessed
from dental_office.roles import staff_required
from patients.models import Patient
from appointments.models import Appointment
from .models import ClaimDenial, Invoice, OfficeSettings, Payment
from .forms import DenialUpdateForm, DenialUploadForm, InvoiceForm, PaymentForm
from .ai import start_analysis

# "[DENTIST TO CONFIRM: ...]"-style gaps the AI leaves for staff to fill in.
PLACEHOLDER_RE = re.compile(r'\[[^\]\n]{2,}\]')


@staff_required
def invoice_list(request):
    status = request.GET.get('status', '')
    invoices = Invoice.objects.select_related('patient', 'appointment').prefetch_related('payments')
    if status:
        invoices = invoices.filter(status=status)
    return render(request, 'billing/invoice_list.html', {
        'invoices': invoices,
        'status_filter': status,
    })


@staff_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    accessed.send(sender=Invoice, instance=invoice)
    payment_form = PaymentForm()
    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'payment_form': payment_form,
        'denials': invoice.denials.all(),
        'denial_form': DenialUploadForm(),
        'ai_phi_allowed': settings.AI_PHI_ALLOWED,
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
        except (Appointment.DoesNotExist, ValueError):
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
        else:
            errors = ' '.join(e for field in form.errors.values() for e in field)
            messages.error(request, f'Payment not recorded: {errors}')
    return redirect('invoice_detail', pk=invoice_pk)


@staff_required
@require_POST
def denial_upload(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    form = DenialUploadForm(
        request.POST, request.FILES,
        require_no_phi_confirmation=not settings.AI_PHI_ALLOWED,
    )
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect('invoice_detail', pk=invoice.pk)
    denial = ClaimDenial.objects.create(
        invoice=invoice, letter=form.cleaned_data['letter'], created_by=request.user,
    )
    start_analysis(denial)
    return redirect('denial_detail', pk=denial.pk)


@staff_required
def denial_list(request):
    show = request.GET.get('show', 'open')
    denials = ClaimDenial.objects.select_related('invoice__patient')
    if show == 'closed':
        denials = denials.exclude(status__in=ClaimDenial.OPEN_STATUSES).order_by('-created_at')
    else:
        show = 'open'
        # Soonest deadline first; letters with no deadline go last.
        denials = sorted(
            denials.filter(status__in=ClaimDenial.OPEN_STATUSES),
            key=lambda d: (d.appeal_deadline is None, d.appeal_deadline or d.created_at.date()),
        )
    return render(request, 'billing/denial_list.html', {'denials': denials, 'show': show})


@staff_required
def denial_detail(request, pk):
    denial = get_object_or_404(ClaimDenial.objects.select_related('invoice__patient'), pk=pk)
    accessed.send(sender=ClaimDenial, instance=denial)
    if request.method == 'POST':
        form = DenialUpdateForm(request.POST, instance=denial)
        if form.is_valid():
            form.save()
            messages.success(request, 'Saved.')
            return redirect('denial_detail', pk=denial.pk)
    else:
        form = DenialUpdateForm(instance=denial)
    return render(request, 'billing/denial_detail.html', {
        'denial': denial,
        'form': form,
        'ai_phi_allowed': settings.AI_PHI_ALLOWED,
        'placeholder_count': len(PLACEHOLDER_RE.findall(denial.appeal_letter or '')),
    })


@staff_required
@require_POST
def denial_retry(request, pk):
    denial = get_object_or_404(ClaimDenial, pk=pk)
    if denial.ai_status == 'processing' and not denial.ai_is_stuck:
        return redirect('denial_detail', pk=denial.pk)
    start_analysis(denial)
    return redirect('denial_detail', pk=denial.pk)


@staff_required
def denial_letter_file(request, pk):
    """Serves the uploaded letter through a staff-only view rather than a
    public media URL, since it contains PHI."""
    denial = get_object_or_404(ClaimDenial, pk=pk)
    accessed.send(sender=ClaimDenial, instance=denial)
    content_type = mimetypes.guess_type(denial.letter.name)[0] or 'application/octet-stream'
    return FileResponse(denial.letter.open('rb'), content_type=content_type)


@staff_required
def denial_print(request, pk):
    denial = get_object_or_404(ClaimDenial.objects.select_related('invoice__patient'), pk=pk)
    accessed.send(sender=ClaimDenial, instance=denial)
    return render(request, 'billing/denial_print.html', {
        'denial': denial,
        'office': OfficeSettings.load(),
    })
