from django.urls import path

from . import views

urlpatterns = [
    path('patients/<int:patient_pk>/', views.staff_image_list, name='staff_image_list'),
    path('patients/<int:patient_pk>/upload/', views.staff_image_upload, name='staff_image_upload'),
    path('<int:pk>/', views.staff_image_detail, name='staff_image_detail'),
    path('<int:pk>/delete/', views.staff_image_delete, name='staff_image_delete'),
]
