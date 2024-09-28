from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib import messages
from .models import EmployeeProfile, Attendance
import qrcode
from io import BytesIO
from datetime import datetime
import cv2
from pyzbar.pyzbar import decode
import os
import csv
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.urls import reverse

# QR Code Generation Function
def generate_unique_qr_code(user):
    try:
        qr_data = f"EmployeeID:{user.id}-LoginTime:{datetime.now()}"
        qr_img = qrcode.make(qr_data)

        buffer = BytesIO()
        qr_img.save(buffer, format="PNG")
        qr_filename = f"qr_{user.username}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        user.employeeprofile.qr_code.save(qr_filename, File(buffer))

        return buffer
    except Exception as e:
        print(f"Error generating QR code: {e}")
        return None

# Register View
def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        password = request.POST.get('password')

        try:
            if User.objects.filter(username=username).exists():
                return HttpResponse('Username already exists')
            elif User.objects.filter(email=email).exists():
                return HttpResponse('Email already registered')
            else:
                user = User.objects.create_user(
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=password
                )
                user.save()

                # Create EmployeeProfile after user registration
                EmployeeProfile.objects.create(user=user)

                auth_login(request, user)
                messages.success(request, 'Registration successful!')
                return redirect('login')
        except Exception as e:
            return HttpResponse(f'Error occurred: {e}')

    return render(request, 'register.html')

# Login View
def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
    
        try:
            user = User.objects.get(email=email)
            user = authenticate(request, username=user.username, password=password)
            if user is not None:
                auth_login(request, user)

                # Generate a unique QR code for the user
                buffer = generate_unique_qr_code(user)

                if buffer:
                    # Create and send the email with the QR code attached to the user's email
                    email_message = EmailMessage(
                        'Your Unique Login QR Code',
                        'Here is your unique QR code for secure login/logout.',
                        from_email=settings.EMAIL_HOST_USER,
                        to=[user.email]
                    )
                    email_message.attach('qr_code.png', buffer.getvalue(), 'image/png')
                    email_message.send()

                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid credentials. Please try again.')
                return redirect('login')
        except User.DoesNotExist:
            messages.error(request, 'Email not registered.')
            return redirect('login')
        except Exception as e:
            messages.error(request, f'An error occurred: {e}')
            return redirect('login')

    return render(request, 'login.html')

# Dashboard View
@login_required
def dashboard(request):
    try:
        attendance_records = Attendance.objects.filter(employee__user=request.user)
        total_views = request.session.get('total_views', 0) + 1  # Increment total views
        request.session['total_views'] = total_views  # Save updated total views in session

        return render(request, 'dashboard.html', {
            'attendance_records': attendance_records,
            'total_views': total_views,  # Pass total views to the template
        })
    except Exception as e:
        messages.error(request, f'Error occurred: {e}')
        return redirect('home')

# QR Code Scanning View for Login/Logout
@login_required
def scan_qr_code(request):
    try:
        cap = cv2.VideoCapture(0)
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            decoded_objects = decode(frame)
            for obj in decoded_objects:
                qr_data = obj.data.decode('utf-8')
                if f"EmployeeID:{request.user.id}" in qr_data:
                    now = datetime.now()
                    attendance_record = Attendance.objects.filter(employee__user=request.user, is_logged_in=True).first()

                    if attendance_record:
                        attendance_record.logout_time = now
                        attendance_record.is_logged_in = False
                        attendance_record.save()
                        message = f'Logout successful at {now.strftime("%Y-%m-%d %H:%M:%S")}'
                    else:
                        Attendance.objects.create(employee=request.user.employeeprofile, login_time=now, is_logged_in=True)
                        message = f'Login successful at {now.strftime("%Y-%m-%d %H:%M:%S")}'

                    cap.release()
                    cv2.destroyAllWindows()
                    return HttpResponse(message)

            cv2.imshow('QR Code Scanner', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()
        return HttpResponse("Invalid QR code or no QR code detected.")
    except Exception as e:
        cap.release()
        cv2.destroyAllWindows()
        return HttpResponse(f"Error occurred: {e}")

# Function to save attendance to CSV
def save_attendance_to_csv():
    try:
        file_path = os.path.join(settings.BASE_DIR, 'attendance_records.csv')
        with open(file_path, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Username', 'Email ID', 'Login Time', 'Logout Time', 'Date'])
            records = Attendance.objects.all()
            for record in records:
                writer.writerow([
                    record.employee.user.username,
                    record.employee.user.email,
                    record.login_time if record.login_time else '',
                    record.logout_time if record.logout_time else '',
                    record.login_time.date() if record.login_time else ''
                ])
    except PermissionError as e:
        print(f"PermissionError: {e}")
    except Exception as e:
        print(f"Error occurred while saving CSV: {e}")

# Forgot Password Request View
def forgot_password_request(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        user = User.objects.filter(username=username, email=email).first()

        if user:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            reset_link = request.build_absolute_uri(
                reverse('reset_password', kwargs={'uidb64': uid, 'token': token})
            )

            email_subject = 'Password Reset Request'
            email_body = f'Click the link to reset your password: {reset_link}'
            email_message = EmailMessage(
                email_subject,
                email_body,
                from_email=settings.EMAIL_HOST_USER,
                to=[email]
            )
            email_message.send()

            messages.success(request, 'Password reset link has been sent to your email.')
            return redirect('login')
        else:
            messages.error(request, 'Invalid username or email.')

    return render(request, 'forgot_password_request.html')

# Password Reset View
def password_reset_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                return redirect('login')  # Redirect to login page after successful password reset
        else:
            form = SetPasswordForm(user)
        return render(request, 'reset_password.html', {'form': form})
    else:
        messages.error(request, 'The password reset link is invalid or has expired.')
        return redirect('login')

# Logout View
@login_required
def logout_view(request):
    auth_logout(request)  # This will log out the user
    messages.success(request, 'You have successfully logged out.')
    return redirect('login')  # Redirect to the login page after logout
