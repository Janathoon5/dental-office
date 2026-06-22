from django.urls import path
from . import views

urlpatterns = [
    path('', views.invoice_list, name='invoice_list'),
    path('add/', views.invoice_add, name='invoice_add'),
    path('<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('<int:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('<int:invoice_pk>/payments/add/', views.payment_add, name='payment_add'),
]
