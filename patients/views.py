from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Patient, MedicalAlert
from .forms import PatientForm, MedicalAlertForm


@login_required
def patient_list(request):
    query = request.GET.get('q', '')
    patients = Patient.objects.all()
    if query:
        patients = patients.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(phone__icontains=query)
        )
    return render(request, 'patients/patient_list.html', {'patients': patients, 'query': query})


@login_required
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    appointments = patient.appointments.order_by('-date', '-start_time')
    alert_form = MedicalAlertForm()
    return render(request, 'patients/patient_detail.html', {
        'patient': patient,
        'appointments': appointments,
        'alert_form': alert_form,
    })


@login_required
def alert_add(request, patient_pk):
    patient = get_object_or_404(Patient, pk=patient_pk)
    if request.method == 'POST':
        form = MedicalAlertForm(request.POST)
        if form.is_valid():
            alert = form.save(commit=False)
            alert.patient = patient
            alert.save()
    return redirect('patient_detail', pk=patient_pk)


@login_required
def alert_delete(request, pk):
    alert = get_object_or_404(MedicalAlert, pk=pk)
    patient_pk = alert.patient.pk
    if request.method == 'POST':
        alert.delete()
    return redirect('patient_detail', pk=patient_pk)


@login_required
def patient_add(request):
    if request.method == 'POST':
        form = PatientForm(request.POST)
        if form.is_valid():
            patient = form.save()
            return redirect('patient_detail', pk=patient.pk)
    else:
        form = PatientForm()
    return render(request, 'patients/patient_form.html', {'form': form, 'title': 'Add Patient'})


@login_required
def patient_edit(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.method == 'POST':
        form = PatientForm(request.POST, instance=patient)
        if form.is_valid():
            form.save()
            return redirect('patient_detail', pk=patient.pk)
    else:
        form = PatientForm(instance=patient)
    return render(request, 'patients/patient_form.html', {'form': form, 'title': 'Edit Patient', 'patient': patient})
