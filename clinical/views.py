from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from dental_office.roles import dentist_required, staff_required
from patients.models import Patient
from appointments.models import Appointment
from .models import TreatmentRecord, TreatmentPlan, TreatmentPlanItem
from .forms import TreatmentRecordForm, TreatmentPlanForm, TreatmentPlanItemForm


@dentist_required
def record_add(request, patient_pk):
    patient = get_object_or_404(Patient, pk=patient_pk)
    initial = {'patient': patient}
    appt_pk = request.GET.get('appointment')
    if appt_pk:
        try:
            appt = Appointment.objects.get(pk=appt_pk, patient=patient)
            initial['appointment'] = appt
            initial['date'] = appt.date
            initial['dentist'] = appt.dentist
        except Appointment.DoesNotExist:
            pass

    if request.method == 'POST':
        form = TreatmentRecordForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('patient_detail', pk=patient_pk)
    else:
        form = TreatmentRecordForm(initial=initial)
        form.fields['patient'].widget = form.fields['patient'].hidden_widget()

    return render(request, 'clinical/record_form.html', {
        'form': form, 'patient': patient, 'title': 'Add Treatment Record'
    })


@dentist_required
def record_edit(request, pk):
    record = get_object_or_404(TreatmentRecord, pk=pk)
    if request.method == 'POST':
        form = TreatmentRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            return redirect('patient_detail', pk=record.patient.pk)
    else:
        form = TreatmentRecordForm(instance=record)
    return render(request, 'clinical/record_form.html', {
        'form': form, 'patient': record.patient, 'title': 'Edit Treatment Record', 'record': record
    })


@dentist_required
def plan_add(request, patient_pk):
    patient = get_object_or_404(Patient, pk=patient_pk)
    if request.method == 'POST':
        form = TreatmentPlanForm(request.POST)
        if form.is_valid():
            plan = form.save()
            return redirect('plan_detail', pk=plan.pk)
    else:
        form = TreatmentPlanForm(initial={'patient': patient})
        form.fields['patient'].widget = form.fields['patient'].hidden_widget()
    return render(request, 'clinical/plan_form.html', {
        'form': form, 'patient': patient, 'title': 'New Treatment Plan'
    })


@staff_required
def plan_detail(request, pk):
    plan = get_object_or_404(TreatmentPlan, pk=pk)
    item_form = TreatmentPlanItemForm()
    if request.method == 'POST':
        item_form = TreatmentPlanItemForm(request.POST)
        if item_form.is_valid():
            item = item_form.save(commit=False)
            item.plan = plan
            item.save()
            return redirect('plan_detail', pk=pk)
    return render(request, 'clinical/plan_detail.html', {
        'plan': plan, 'item_form': item_form
    })


@dentist_required
def plan_item_toggle(request, pk):
    item = get_object_or_404(TreatmentPlanItem, pk=pk)
    item.status = 'completed' if item.status == 'pending' else 'pending'
    item.save()
    return redirect('plan_detail', pk=item.plan.pk)
