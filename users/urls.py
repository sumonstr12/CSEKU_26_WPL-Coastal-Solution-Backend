from django.urls import path
from .views import *
from users.jwt_token.views import CookieTokenRefreshView

urlpatterns = [
    path('auth/register/request/', RegisterRequestView.as_view(), name='register-request'),
    path('auth/register/verify/', RegisterVerifyView.as_view(), name='register-verify'),
    path('auth/register/resend/', RegisterResendView.as_view(), name='register-resend'),


    path('auth/login/', UserLoginView.as_view(), name='user-login'),
    path('auth/logout/', UserLogoutView.as_view(), name='user-logout'),


    path('forget-password/', ForgetPasswordView.as_view(), name='forget-password'),
    path('verify-password-otp/', VerifyPasswordResetOTPAPIView.as_view(), name='verify-password-otp'),
    path('reset-password/', ResetPasswordAPIView.as_view(), name='reset-password'),

    path('users/me/', UserProfileView.as_view(), name='user-profile'),
    path('users/me/profile/', UserInfoView.as_view(), name='user-profile-info'),



    path('token/get-refresh/', CookieTokenRefreshView.as_view()),



]