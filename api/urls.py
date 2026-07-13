from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('auth/login/', views.PatientTokenObtainPairView.as_view(), name='api_login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    path('dashboard/', views.DashboardView.as_view(), name='api_dashboard'),
    path('profile/', views.ProfileView.as_view(), name='api_profile'),
]
