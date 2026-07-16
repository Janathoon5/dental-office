from django.urls import path
from . import views

urlpatterns = [
    path('patients/<int:patient_pk>/send/', views.staff_send_message, name='staff_send_message'),
]
