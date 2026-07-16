from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('auth/login/', views.PatientTokenObtainPairView.as_view(), name='api_login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    path('auth/accept-invite/', views.AcceptInviteView.as_view(), name='api_accept_invite'),
    path('dashboard/', views.DashboardView.as_view(), name='api_dashboard'),
    path('profile/', views.ProfileView.as_view(), name='api_profile'),
    path('appointments/', views.AppointmentListView.as_view(), name='api_appointments'),
    path('appointment-requests/', views.AppointmentRequestListCreateView.as_view(), name='api_appointment_requests'),
    path('appointment-requests/<int:pk>/', views.AppointmentRequestDetailView.as_view(), name='api_appointment_request_detail'),
    path('records/treatment-records/', views.TreatmentRecordListView.as_view(), name='api_treatment_records'),
    path('records/treatment-plans/', views.TreatmentPlanListView.as_view(), name='api_treatment_plans'),
    path('invoices/', views.InvoiceListView.as_view(), name='api_invoices'),
    path('messages/', views.MessageListCreateView.as_view(), name='api_messages'),
    path('messages/mark-read/', views.MarkMessagesReadView.as_view(), name='api_messages_mark_read'),
    path('devices/register/', views.RegisterDeviceView.as_view(), name='api_register_device'),
]
