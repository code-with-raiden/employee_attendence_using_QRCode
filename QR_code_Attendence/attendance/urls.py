from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),  # Login view
    path('dashboard/', views.dashboard, name='dashboard'),  # Dashboard view
    path('scan_qr_code/', views.scan_qr_code, name='scan_qr_code'),  # QR Code scan view
    path('register/', views.register_view, name='register'),  # Add the register view
    path('forgot_password/', views.forgot_password_request, name='forgot_password'),
    path('reset_password/<uidb64>/<token>/', views.password_reset_view, name='reset_password'),
    path('logout/', views.logout_view, name='logout'),
]
