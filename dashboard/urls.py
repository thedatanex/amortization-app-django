from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("generate_amortization/", views.generate_amortization, name="generate_amortization"),
    path("generate_amortization_multiple/", views.generate_amortization_multiple, name="generate_amortization_multiple"),
    path("detect_anomalies/", views.detect_anomalies, name="detect_anomalies"),  # ✅ AI anomaly detection endpoint
    path('get_fraud_data/', views.get_fraud_data, name='get_fraud_data'),  # New endpoint
]
