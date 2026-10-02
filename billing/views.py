import mimetypes

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from auditlog.signals import accessed
from dental_office.roles import is_dentist, staff_required
from patients.models import Patient
from appointments.models import Appointment
from .models import AIUsage, ClaimDenial, Invoice, InvoiceLineItem, OfficeSettings, Payment
from .forms import DenialUpdateForm, DenialUploadForm, InvoiceForm, InvoiceLineItemForm, PaymentForm
from .cdt import COMMON_CODES
from dental_office.templatetags.office import money
from .packet import build_packet, packet_options
from .ai import start_ai_task, start_analysis, start_revision
from .placeholders import CATEGORY_LABELS, count_by_category, find_placeholders


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
    return _invoice_page(request, invoice)


def _invoice_page(request, invoice, payment_form=None):
    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'payment_form': payment_form or PaymentForm(invoice=invoice),
        'voided_payments': invoice.voided_payments(),
        'line_items': invoice.line_items.all(),
        'line_form': InvoiceLineItemForm(initial={
            'service_date': (invoice.appointment.date if invoice.appointment else timezone.localdate()).isoformat(),
        }),
        'common_codes': COMMON_CODES,
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
@require_POST
def line_item_add(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    form = InvoiceLineItemForm(request.POST)
    if form.is_valid():
        line = form.save(commit=False)
        line.invoice = invoice
        line.save()
        invoice.recalculate_subtotal()
    else:
        for field, errors in form.errors.items():
            label = form.fields[field].label if field in form.fields else ''
            for error in errors:
                messages.error(request, f'{label}: {error}' if label else error)
    return redirect('invoice_detail', pk=invoice.pk)


@staff_required
@require_POST
def line_item_delete(request, pk):
    line = get_object_or_404(InvoiceLineItem, pk=pk)
    invoice = line.invoice
    line.delete()
    invoice.recalculate_subtotal()
    return redirect('invoice_detail', pk=invoice.pk)


@staff_required
def payment_add(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    if request.method == 'POST':
        form = PaymentForm(request.POST, invoice=invoice)
        if not form.is_valid():
            # Show the form again with the amount kept, so a typo can be
            # fixed or an overpayment confirmed.
            return _invoice_page(request, invoice, payment_form=form)
        payment = form.save(commit=False)
        payment.invoice = invoice
        payment.save()
        invoice.update_status()
        text = f'Recorded a {money(payment.amount)} {payment.get_method_display().lower()} payment.'
        if invoice.credit():
            text += f' {money(invoice.credit())} is kept as a credit.'
        messages.success(request, text)
    return redirect('invoice_detail', pk=invoice_pk)


@staff_required
@require_POST
def payment_void(request, pk):
    """Undo a payment recorded by mistake. It stays on the invoice, crossed
    out, with who voided it, when and why."""
    payment = get_object_or_404(Payment, pk=pk)
    invoice = payment.invoice
    reason = request.POST.get('reason', '').strip()[:200]
    if not reason:
        messages.error(request, 'Type a reason to void a payment, e.g. "Entered 3600 instead of 36.00".')
        return redirect('invoice_detail', pk=invoice.pk)
    payment.void_reason = reason
    payment.save(update_fields=['void_reason'])
    payment.delete(deleted_by=request.user)
    invoice.update_status()
    messages.success(request, f'Voided the {money(payment.amount)} payment from {payment.date:%b} {payment.date.day}. '
                              f'The balance due is now {money(invoice.balance_due())}.')
    return redirect('invoice_detail', pk=invoice.pk)


@staff_required
@require_POST
def denial_upload(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    if AIUsage.limit_reached(request.user):
        messages.error(request, "Today's AI limit for the demo has been reached. "
                       'The preloaded denials show finished examples, or try again tomorrow.')
        return redirect('invoice_detail', pk=invoice.pk)
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
    start_analysis(denial, request.user)
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
    denials = list(denials)
    for d in denials:
        d.open_item_count = len(find_placeholders(d.appeal_letter))
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
        'open_items': count_by_category(denial.appeal_letter),
        'category_labels': CATEGORY_LABELS,
    })


@staff_required
@require_POST
def denial_retry(request, pk):
    denial = get_object_or_404(ClaimDenial, pk=pk)
    if denial.ai_status == 'processing' and not denial.ai_is_stuck:
        return redirect('denial_detail', pk=denial.pk)
    # "Re-run AI" asks for a fresh analysis; "Try again" repeats whichever task failed.
    if AIUsage.limit_reached(request.user):
        messages.error(request, "Today's AI limit for the demo has been reached. "
                       'The preloaded denials show finished examples, or try again tomorrow.')
        return redirect('denial_detail', pk=denial.pk)
    task = request.POST.get('task') if request.POST.get('task') in ('analyze', 'revise') else denial.ai_task
    start_ai_task(denial, task, request.user)
    return redirect('denial_detail', pk=denial.pk)


def _can_answer_clinical(user):
    return user.is_superuser or is_dentist(user)


@staff_required
def denial_review(request, pk):
    """Checklist of the letter's [BRACKETED] items. The team answers them
    here, then the AI works the answers into the letter."""
    denial = get_object_or_404(ClaimDenial.objects.select_related('invoice__patient'), pk=pk)
    accessed.send(sender=ClaimDenial, instance=denial)
    if denial.ai_status != 'done':
        return redirect('denial_detail', pk=denial.pk)

    can_answer_clinical = _can_answer_clinical(request.user)
    items = find_placeholders(denial.appeal_letter)
    # Pre-fill from earlier answers, e.g. when the AI update failed and they retry.
    previous = {a['placeholder']: a for a in denial.review_answers}
    for i, item in enumerate(items):
        item['index'] = i
        item['locked'] = item['category'] == 'dentist' and not can_answer_clinical
        item['previous'] = previous.get(item['placeholder'], {})

    if request.method == 'POST':
        by_text = {item['placeholder']: item for item in items}
        answers = []
        for i in range(len(items)):
            item = by_text.get(request.POST.get(f'ph_{i}', ''))
            if item is None:
                messages.error(request, 'The letter changed while you were filling this in. Please check the list again.')
                return redirect('denial_review', pk=denial.pk)
            if item['locked']:
                continue  # clinical facts must come from a dentist
            answer = request.POST.get(f'answer_{i}', '').strip()
            remove = request.POST.get(f'remove_{i}') == 'on'
            attach = request.POST.get(f'attach_{i}') == 'on'
            if item['category'] == 'attach' and not (attach or remove):
                continue
            if item['category'] != 'attach' and not (answer or remove):
                continue
            answers.append({
                'placeholder': item['placeholder'],
                'category': item['category'],
                'question': item['question'],
                'answer': '' if remove else answer,
                'remove': remove,
                'answered_by': request.user.get_full_name() or request.user.username,
            })
        if not answers:
            messages.error(request, 'Answer or check at least one item first.')
            return redirect('denial_review', pk=denial.pk)
        if AIUsage.limit_reached(request.user):
            messages.error(request, "Today's AI limit for the demo has been reached. "
                       'The preloaded denials show finished examples, or try again tomorrow.')
            return redirect('denial_review', pk=denial.pk)
        denial.review_answers = answers
        denial.save(update_fields=['review_answers_json'])
        start_revision(denial, request.user)
        return redirect('denial_detail', pk=denial.pk)

    groups = [
        (key, label, [item for item in items if item['category'] == key])
        for key, label in CATEGORY_LABELS.items()
    ]
    return render(request, 'billing/denial_review.html', {
        'denial': denial,
        'groups': [g for g in groups if g[2]],
        'item_count': len(items),
        'can_answer_clinical': can_answer_clinical,
    })


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


@staff_required
def denial_packet(request, pk):
    """Pick what goes in the appeal packet, then download it as one PDF."""
    denial = get_object_or_404(ClaimDenial.objects.select_related('invoice__patient', 'invoice__appointment'), pk=pk)
    accessed.send(sender=ClaimDenial, instance=denial)
    if denial.ai_status != 'done':
        return redirect('denial_detail', pk=denial.pk)
    records, images = packet_options(denial)

    if request.method == 'POST':
        record_ids = set(request.POST.getlist('records'))
        image_ids = set(request.POST.getlist('images'))
        pdf = build_packet(
            denial, OfficeSettings.load(),
            records=[r['obj'] for r in records if str(r['obj'].pk) in record_ids],
            images=[i['obj'] for i in images if str(i['obj'].pk) in image_ids],
            include_summary=request.POST.get('summary') == 'on',
            include_original=request.POST.get('original') == 'on',
        )
        patient = denial.invoice.patient
        name = f'Appeal packet - {patient.last_name} - {denial.claim_number or f"invoice {denial.invoice.pk}"}.pdf'
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{name.replace(chr(34), "")}"'
        return response

    return render(request, 'billing/denial_packet.html', {
        'denial': denial,
        'records': records,
        'images': images,
        'open_items': len(find_placeholders(denial.appeal_letter)),
        'ai_phi_allowed': settings.AI_PHI_ALLOWED,
    })
