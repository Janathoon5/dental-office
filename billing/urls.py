from django.urls import path
from . import views

urlpatterns = [
    path('', views.invoice_list, name='invoice_list'),
    path('add/', views.invoice_add, name='invoice_add'),
    path('<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('<int:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('<int:invoice_pk>/payments/add/', views.payment_add, name='payment_add'),
    path('payments/<int:pk>/void/', views.payment_void, name='payment_void'),
    path('<int:invoice_pk>/procedures/add/', views.line_item_add, name='line_item_add'),
    path('procedures/<int:pk>/delete/', views.line_item_delete, name='line_item_delete'),
    path('<int:invoice_pk>/denials/upload/', views.denial_upload, name='denial_upload'),
    path('denials/', views.denial_list, name='denial_list'),
    path('denials/<int:pk>/', views.denial_detail, name='denial_detail'),
    path('denials/<int:pk>/retry/', views.denial_retry, name='denial_retry'),
    path('denials/<int:pk>/review/', views.denial_review, name='denial_review'),
    path('denials/<int:pk>/letter/', views.denial_letter_file, name='denial_letter_file'),
    path('denials/<int:pk>/print/', views.denial_print, name='denial_print'),
    path('denials/<int:pk>/packet/', views.denial_packet, name='denial_packet'),
]
