from django.urls import path
from . import views

urlpatterns = [
    path('2fa/setup/', views.setup_2fa, name='setup_2fa'),
    path('2fa/disable/', views.disable_2fa, name='disable_2fa'),
]
