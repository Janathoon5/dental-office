from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from dental_office.roles import is_patient
from appointments.models import Appointment, AppointmentRequest
from billing.models import Invoice
from clinical.models import TreatmentRecord, TreatmentPlan, TreatmentPlanItem
from messaging.models import DeviceToken, Message
from patients.models import Patient
from patient_portal.models import PatientInvite
from patient_portal.validators import validate_office_hours


class PatientTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Same as simplejwt's default, but rejects non-patient accounts. Staff
    use the web dashboard, not this API. Runs after authenticate() succeeds,
    so django-axes lockout (wired into AUTHENTICATION_BACKENDS) still applies
    to bad credentials before this check is ever reached."""

    def validate(self, attrs):
        data = super().validate(attrs)
        if not is_patient(self.user):
            raise serializers.ValidationError('This account does not have patient portal access.')
        return data


class AppointmentSerializer(serializers.ModelSerializer):
    dentist_name = serializers.CharField(source='dentist.get_full_name', default='', read_only=True)

    class Meta:
        model = Appointment
        fields = [
            'id', 'date', 'start_time', 'duration_minutes',
            'appointment_type', 'status', 'dentist_name',
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    patient_owes = serializers.SerializerMethodField()
    amount_paid = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'date_issued', 'subtotal', 'insurance_amount', 'status',
            'patient_owes', 'amount_paid', 'balance_due',
        ]

    def get_patient_owes(self, obj):
        return obj.patient_owes()

    def get_amount_paid(self, obj):
        return obj.amount_paid()

    def get_balance_due(self, obj):
        return obj.balance_due()


class PatientProfileSerializer(serializers.ModelSerializer):
    """Deliberately whitelisted to the same 3 fields patient_profile lets a
    patient edit on the web (patient_portal/forms.py:PatientProfileForm) —
    never fields='__all__' here, since Patient also has medical/insurance
    fields patients aren't allowed to touch."""

    class Meta:
        model = Patient
        fields = ['phone', 'email', 'address']


class PatientDashboardSerializer(serializers.Serializer):
    """Not a ModelSerializer — mirrors patient_portal/views.py:patient_dashboard,
    which aggregates data across models rather than serializing one."""
    first_name = serializers.CharField()
    next_appointment = AppointmentSerializer(allow_null=True)
    total_balance = serializers.DecimalField(max_digits=10, decimal_places=2)


class AppointmentRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppointmentRequest
        fields = [
            'id', 'preferred_date', 'preferred_time', 'appointment_type',
            'message', 'status', 'submitted_at',
        ]
        read_only_fields = ['status', 'submitted_at']

    def validate_preferred_date(self, value):
        # localdate(), not date.today(): the server runs UTC, so after 8pm
        # Eastern date.today() is already tomorrow and would reject a
        # request for what is still today at the office.
        if value < timezone.localdate():
            raise serializers.ValidationError('Please choose a future date.')
        return value

    def validate(self, attrs):
        preferred_date = attrs.get(
            'preferred_date', getattr(self.instance, 'preferred_date', None)
        )
        preferred_time = attrs.get(
            'preferred_time', getattr(self.instance, 'preferred_time', None)
        )
        try:
            validate_office_hours(preferred_date, preferred_time)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict)
        return attrs


class TreatmentRecordSerializer(serializers.ModelSerializer):
    dentist_name = serializers.CharField(source='dentist.get_full_name', default='', read_only=True)
    # EncryptedTextField isn't recognized by DRF's automatic field mapping.
    notes = serializers.CharField(read_only=True)

    class Meta:
        model = TreatmentRecord
        fields = ['id', 'date', 'procedure', 'tooth_number', 'notes', 'dentist_name']


class TreatmentPlanItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreatmentPlanItem
        fields = ['id', 'procedure', 'tooth_number', 'estimated_cost', 'status']


class TreatmentPlanSerializer(serializers.ModelSerializer):
    notes = serializers.CharField(read_only=True)
    items = TreatmentPlanItemSerializer(many=True, read_only=True)
    total_cost = serializers.SerializerMethodField()

    class Meta:
        model = TreatmentPlan
        fields = ['id', 'title', 'created_date', 'status', 'notes', 'items', 'total_cost']

    def get_total_cost(self, obj):
        return obj.total_cost()


class AcceptInviteSerializer(serializers.Serializer):
    """Mobile equivalent of patient_portal/views.py:accept_invite — validates
    the invite token and new password, then the view mints a token pair
    directly so the app can log the patient straight in."""
    token = serializers.UUIDField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        try:
            invite = PatientInvite.objects.select_related('patient__user').get(
                token=attrs['token']
            )
        except PatientInvite.DoesNotExist:
            raise serializers.ValidationError('Invalid or expired invite link.')

        if not invite.is_valid() or not invite.patient.user:
            raise serializers.ValidationError('This invite link has expired or already been used.')

        attrs['invite'] = invite
        return attrs


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.get_full_name', default='', read_only=True)
    is_from_staff = serializers.SerializerMethodField()
    # EncryptedTextField isn't recognized by DRF's automatic field mapping.
    body = serializers.CharField()

    class Meta:
        model = Message
        fields = ['id', 'sender_name', 'is_from_staff', 'body', 'sent_at', 'read_at']
        read_only_fields = ['sent_at', 'read_at']

    def get_is_from_staff(self, obj):
        return bool(obj.sender) and not is_patient(obj.sender)


class DeviceTokenSerializer(serializers.Serializer):
    fcm_token = serializers.CharField(max_length=255)
    platform = serializers.ChoiceField(choices=DeviceToken.PLATFORM_CHOICES)
