from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('generate_amortization/', views.generate_amortization, name='generate_amortization'),
]