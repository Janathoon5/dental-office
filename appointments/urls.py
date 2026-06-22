from django.urls import path
from . import views

urlpatterns = [
    path('', views.appointment_list, name='appointment_list'),
    path('add/', views.appointment_add, name='appointment_add'),
    path('request/', views.appointment_request, name='appointment_request'),
    path('requests/', views.request_list, name='request_list'),
    path('requests/<int:pk>/update/', views.request_update, name='request_update'),
    path('reminders/', views.reminders_dashboard, name='reminders_dashboard'),
    path('reminders/send/', views.send_reminders_now, name='send_reminders_now'),
    path('<int:pk>/', views.appointment_detail, name='appointment_detail'),
    path('<int:pk>/edit/', views.appointment_edit, name='appointment_edit'),
    path('<int:pk>/cancel/', views.appointment_cancel, name='appointment_cancel'),
]
