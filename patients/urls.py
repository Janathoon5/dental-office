from django.urls import path
from . import views

urlpatterns = [
    path('', views.patient_list, name='patient_list'),
    path('add/', views.patient_add, name='patient_add'),
    path('<int:pk>/', views.patient_detail, name='patient_detail'),
    path('<int:pk>/edit/', views.patient_edit, name='patient_edit'),
    path('<int:pk>/invite/', views.send_patient_invite, name='send_patient_invite'),
    path('<int:patient_pk>/alerts/add/', views.alert_add, name='alert_add'),
    path('alerts/<int:pk>/delete/', views.alert_delete, name='alert_delete'),
]
