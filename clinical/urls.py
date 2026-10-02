from django.urls import path
from . import views

urlpatterns = [
    path('patients/<int:patient_pk>/records/add/', views.record_add, name='record_add'),
    path('records/<int:pk>/', views.record_detail, name='record_detail'),
    path('records/<int:pk>/edit/', views.record_edit, name='record_edit'),
    path('patients/<int:patient_pk>/plans/add/', views.plan_add, name='plan_add'),
    path('plans/<int:pk>/', views.plan_detail, name='plan_detail'),
    path('plans/<int:pk>/edit/', views.plan_edit, name='plan_edit'),
    path('plans/items/<int:pk>/edit/', views.plan_item_edit, name='plan_item_edit'),
    path('plans/items/<int:pk>/delete/', views.plan_item_delete, name='plan_item_delete'),
    path('patients/<int:patient_pk>/chart/', views.tooth_chart, name='tooth_chart'),
    path('patients/<int:patient_pk>/chart/<int:tooth>/', views.tooth_update, name='tooth_update'),
    path('plans/items/<int:pk>/toggle/', views.plan_item_toggle, name='plan_item_toggle'),
]
