from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from dental_office.roles import is_patient
from appointments.models import Appointment
from billing.models import Invoice
from patients.models import Patient


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
