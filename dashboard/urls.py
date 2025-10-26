from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),  # or your main view name
]
