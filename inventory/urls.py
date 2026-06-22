from django.urls import path
from . import views

urlpatterns = [
    path('', views.supply_list, name='supply_list'),
    path('add/', views.supply_add, name='supply_add'),
    path('<int:pk>/edit/', views.supply_edit, name='supply_edit'),
    path('<int:pk>/adjust/', views.supply_adjust, name='supply_adjust'),
]
