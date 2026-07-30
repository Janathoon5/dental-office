from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from . import views
from staff.views import login_view, verify_otp

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', login_view, name='login'),
    path('verify-otp/', verify_otp, name='verify_otp'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
    path('account-deletion/', views.account_deletion, name='account_deletion'),
    path('', views.dashboard, name='dashboard'),
    path('patients/', include('patients.urls')),
    path('appointments/', include('appointments.urls')),
    path('clinical/', include('clinical.urls')),
    path('billing/', include('billing.urls')),
    path('inventory/', include('inventory.urls')),
    path('account/', include('staff.urls')),
    path('reports/', views.reports, name='reports'),
    path('patient/', include('patient_portal.urls')),
    path('messaging/', include('messaging.urls')),
    path('imaging/', include('imaging.urls')),
    path('api/v1/', include('api.urls')),
]
