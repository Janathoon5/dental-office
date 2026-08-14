from django.contrib.auth.models import Group
from django.utils import timezone
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from appointments.models import AppointmentRequest
from messaging.models import Conversation, DeviceToken

from .permissions import IsPatient
from .serializers import (
    AcceptInviteSerializer,
    AppointmentRequestSerializer,
    AppointmentSerializer,
    DeviceTokenSerializer,
    InvoiceSerializer,
    MessageSerializer,
    PatientDashboardSerializer,
    PatientProfileSerializer,
    PatientTokenObtainPairSerializer,
    TreatmentPlanSerializer,
    TreatmentRecordSerializer,
)


@method_decorator(ratelimit(key='ip', rate='10/m', block=True), name='post')
class PatientTokenObtainPairView(TokenObtainPairView):
    """Defense-in-depth beyond django-axes: axes locks out a specific
    ip+username pair after repeated failures, but doesn't limit how many
    distinct usernames a single IP can try per minute. This closes that gap."""
    serializer_class = PatientTokenObtainPairSerializer


class DashboardView(APIView):
    permission_classes = [IsPatient]

    def get(self, request):
        patient = request.user.patient_profile
        today = timezone.localdate()

        next_appointment = patient.appointments.filter(
            date__gte=today, status='scheduled'
        ).order_by('date', 'start_time').first()

        total_balance = sum(
            inv.balance_due() for inv in patient.invoices.filter(status__in=['pending', 'partial'])
        )

        data = {
            'first_name': patient.first_name,
            'next_appointment': next_appointment,
            'total_balance': total_balance,
        }
        return Response(PatientDashboardSerializer(data).data)


class ProfileView(APIView):
    permission_classes = [IsPatient]

    def get(self, request):
        serializer = PatientProfileSerializer(request.user.patient_profile)
        return Response(serializer.data)

    def patch(self, request):
        serializer = PatientProfileSerializer(
            request.user.patient_profile, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class AppointmentListView(generics.ListAPIView):
    """?scope=upcoming (default) or ?scope=past, mirroring
    patient_portal/views.py:patient_appointments."""
    serializer_class = AppointmentSerializer
    permission_classes = [IsPatient]

    def get_queryset(self):
        patient = self.request.user.patient_profile
        today = timezone.localdate()
        if self.request.query_params.get('scope') == 'past':
            return patient.appointments.filter(date__lt=today).order_by('-date', '-start_time')[:10]
        return patient.appointments.filter(
            date__gte=today, status='scheduled'
        ).order_by('date', 'start_time')


class AppointmentRequestListCreateView(generics.ListCreateAPIView):
    serializer_class = AppointmentRequestSerializer
    permission_classes = [IsPatient]

    def get_queryset(self):
        patient = self.request.user.patient_profile
        AppointmentRequest.objects.expire_stale()
        return patient.appointment_requests.filter(status='pending')

    def perform_create(self, serializer):
        patient = self.request.user.patient_profile
        serializer.save(
            patient=patient, first_name=patient.first_name,
            last_name=patient.last_name, phone=patient.phone, email=patient.email,
        )


class AppointmentRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Only pending requests are visible/editable here, matching the web
    view's get_object_or_404(..., status='pending') scoping."""
    serializer_class = AppointmentRequestSerializer
    permission_classes = [IsPatient]

    def get_queryset(self):
        patient = self.request.user.patient_profile
        return patient.appointment_requests.filter(status='pending')


class TreatmentRecordListView(generics.ListAPIView):
    serializer_class = TreatmentRecordSerializer
    permission_classes = [IsPatient]

    def get_queryset(self):
        return self.request.user.patient_profile.treatment_records.order_by('-date')


class TreatmentPlanListView(generics.ListAPIView):
    serializer_class = TreatmentPlanSerializer
    permission_classes = [IsPatient]

    def get_queryset(self):
        return self.request.user.patient_profile.treatment_plans.order_by('-created_date')


class InvoiceListView(generics.ListAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [IsPatient]

    def get_queryset(self):
        return self.request.user.patient_profile.invoices.prefetch_related('payments').order_by('-date_issued')


class AcceptInviteView(APIView):
    """Mobile equivalent of patient_portal/views.py:accept_invite. Unauthenticated
    by design (the invite token is the credential) — mints a token pair directly
    so the app can log the patient in without a separate login call."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AcceptInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = serializer.validated_data['invite']
        user = invite.patient.user

        user.set_password(serializer.validated_data['password'])
        user.is_active = True
        user.save()

        patient_group, _ = Group.objects.get_or_create(name='Patient')
        user.groups.add(patient_group)

        invite.used = True
        invite.save()

        refresh = RefreshToken.for_user(user)
        return Response({'access': str(refresh.access_token), 'refresh': str(refresh)})


class MessageListCreateView(generics.ListCreateAPIView):
    """A patient's own conversation is always resolved from their
    authenticated identity (never a client-supplied id), so there's no
    object-level access path to another patient's conversation to guard
    against here."""
    serializer_class = MessageSerializer
    permission_classes = [IsPatient]

    def get_queryset(self):
        patient = self.request.user.patient_profile
        conversation = Conversation.get_or_start_for(patient)
        return conversation.messages.order_by('sent_at')

    def perform_create(self, serializer):
        patient = self.request.user.patient_profile
        conversation = Conversation.get_or_start_for(patient)
        serializer.save(conversation=conversation, sender=self.request.user)


class MarkMessagesReadView(APIView):
    permission_classes = [IsPatient]

    def post(self, request):
        patient = request.user.patient_profile
        try:
            conversation = patient.conversation
        except Conversation.DoesNotExist:
            return Response(status=204)
        conversation.messages.filter(read_at__isnull=True).exclude(
            sender=request.user
        ).update(read_at=timezone.now())
        return Response(status=204)


class RegisterDeviceView(APIView):
    permission_classes = [IsPatient]

    def post(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Use all_objects (not the active-only default manager) so a token
        # that was previously soft-deleted gets reactivated on re-registration
        # instead of hitting the unique constraint on fcm_token.
        DeviceToken.all_objects.update_or_create(
            fcm_token=serializer.validated_data['fcm_token'],
            defaults={
                'patient': request.user.patient_profile,
                'platform': serializer.validated_data['platform'],
                'is_active': True,
                'deleted_at': None,
                'deleted_by': None,
            },
        )
        return Response(status=201)
