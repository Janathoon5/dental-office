from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import PatientTokenObtainPairSerializer, PatientDashboardSerializer, PatientProfileSerializer
from .permissions import IsPatient


class PatientTokenObtainPairView(TokenObtainPairView):
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
