from django.urls import path
from . import views

urlpatterns = [
    path('', views.patient_dashboard, name='patient_dashboard'),
    path('appointments/', views.patient_appointments, name='patient_appointments'),
    path('appointments/request/', views.patient_request_appointment, name='patient_request_appointment'),
    path('appointments/<int:pk>/edit/', views.patient_edit_appointment_request, name='patient_edit_appointment_request'),
    path('appointments/<int:pk>/cancel/', views.patient_cancel_appointment_request, name='patient_cancel_appointment_request'),
    path('records/', views.patient_records, name='patient_records'),
    path('invoices/', views.patient_invoices, name='patient_invoices'),
    path('profile/', views.patient_profile, name='patient_profile'),
    path('invite/<uuid:token>/', views.accept_invite, name='accept_invite'),
]
