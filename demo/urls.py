from django.urls import path

from . import views

urlpatterns = [
    path('login/<str:role>/', views.demo_login, name='demo_login'),
    path('reset/', views.reset_demo, name='reset_demo'),
]
