from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.core.mail import send_mail
from django.db.models import Q
from dental_office.roles import staff_required
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
    patient_has_portal = bool(
        patient.user and
        patient.user.is_active and
        patient.user.groups.filter(name='Patient').exists()
    )
    return render(request, 'patients/patient_detail.html', {
        'patient': patient,
        'appointments': appointments,
        'alert_form': alert_form,
        'patient_has_portal': patient_has_portal,
    })


@staff_required
def send_patient_invite(request, pk):
    if request.method != 'POST':
        return redirect('patient_detail', pk=pk)

    patient = get_object_or_404(Patient, pk=pk)

    if not patient.email:
        messages.error(request, 'This patient has no email address. Add one first before sending an invite.')
        return redirect('patient_detail', pk=pk)

    if patient.user and patient.user.is_active and patient.user.groups.filter(name='Patient').exists():
        messages.info(request, f'{patient.first_name} already has an active portal account.')
        return redirect('patient_detail', pk=pk)

    # Create user account if one doesn't exist yet
    from django.contrib.auth.models import User
    if not patient.user:
        username = patient.email
        if User.objects.filter(username__iexact=username).exists():
            username = f'patient_{patient.pk}'
        user = User.objects.create(
            username=username,
            email=patient.email,
            first_name=patient.first_name,
            last_name=patient.last_name,
            is_active=False,
        )
        user.set_unusable_password()
        user.save()
        patient.user = user
        patient.save()

    # Create a fresh invite token
    from patient_portal.models import PatientInvite
    invite = PatientInvite.objects.create(patient=patient)

    invite_url = request.build_absolute_uri(
        reverse('accept_invite', args=[str(invite.token)])
    )

    send_mail(
        subject='Your Patient Portal Invitation',
        message=(
            f'Hello {patient.first_name},\n\n'
            f'You have been invited to access your patient portal. '
            f'Use it to view your appointments, treatment records, and invoices online.\n\n'
            f'Your username is: {patient.user.username}\n\n'
            f'Set your password here:\n{invite_url}\n\n'
            f'This link expires in 7 days. If you did not expect this email, you can ignore it.\n'
        ),
        from_email=None,
        recipient_list=[patient.email],
    )

    messages.success(request, f'Portal invitation sent to {patient.email}.')
    return redirect('patient_detail', pk=pk)


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
