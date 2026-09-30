from django.urls import path
from . import views

urlpatterns = [
    path('patients/<int:patient_pk>/records/add/', views.record_add, name='record_add'),
    path('records/<int:pk>/edit/', views.record_edit, name='record_edit'),
    path('patients/<int:patient_pk>/plans/add/', views.plan_add, name='plan_add'),
    path('plans/<int:pk>/', views.plan_detail, name='plan_detail'),
    path('patients/<int:patient_pk>/chart/', views.tooth_chart, name='tooth_chart'),
    path('patients/<int:patient_pk>/chart/<int:tooth>/', views.tooth_update, name='tooth_update'),
    path('plans/items/<int:pk>/toggle/', views.plan_item_toggle, name='plan_item_toggle'),
]
