from django.shortcuts import get_object_or_404, redirect
from dental_office.roles import staff_required
from patients.models import Patient
from .models import Conversation, Message


@staff_required
def staff_send_message(request, patient_pk):
    patient = get_object_or_404(Patient, pk=patient_pk)
    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            conversation, _ = Conversation.objects.get_or_create(patient=patient)
            Message.objects.create(conversation=conversation, sender=request.user, body=body)
    return redirect('patient_detail', pk=patient_pk)
