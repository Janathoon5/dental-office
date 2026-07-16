from django.shortcuts import render, get_object_or_404, redirect
from auditlog.signals import accessed

from dental_office.roles import staff_required
from patients.models import Patient
from .forms import StaffImageUploadForm
from .models import DentalImage


@staff_required
def staff_image_list(request, patient_pk):
    patient = get_object_or_404(Patient, pk=patient_pk)
    accessed.send(sender=Patient, instance=patient)
    images = patient.dental_images.order_by('image_type', '-captured_date')
    form = StaffImageUploadForm()
    return render(request, 'imaging/staff_image_list.html', {
        'patient': patient,
        'images': images,
        'form': form,
    })


@staff_required
def staff_image_upload(request, patient_pk):
    patient = get_object_or_404(Patient, pk=patient_pk)
    if request.method == 'POST':
        form = StaffImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            image = form.save(commit=False)
            image.patient = patient
            image.uploaded_by = request.user
            image.uploaded_by_patient = False
            image.save()
    return redirect('staff_image_list', patient_pk=patient_pk)


@staff_required
def staff_image_detail(request, pk):
    image = get_object_or_404(DentalImage, pk=pk)
    accessed.send(sender=DentalImage, instance=image)
    previous_image = DentalImage.objects.filter(
        patient=image.patient,
        image_type=image.image_type,
        captured_date__lt=image.captured_date,
    ).order_by('-captured_date').first()
    return render(request, 'imaging/staff_image_detail.html', {
        'image': image,
        'previous_image': previous_image,
    })


@staff_required
def staff_image_delete(request, pk):
    image = get_object_or_404(DentalImage, pk=pk)
    patient_pk = image.patient_id
    if request.method == 'POST':
        image.delete(deleted_by=request.user)
    return redirect('staff_image_list', patient_pk=patient_pk)
