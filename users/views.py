import random

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.base_user import AbstractBaseUser
from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import *
from .permissions import *
from .serializers import *
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken, BlacklistMixin

from Utilis.send_email import send_email
from Utilis.templates import *

from datetime import timedelta
from django.utils import timezone

from healper_functions.register_helper import *

User = get_user_model()


# Create your views here.
class RegisterRequestView(APIView):
    permission_classes = []

    def post(self, request):
        serializer = RegisterRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        phone_number = data["phone_number"]

        PendingRegistration.objects.filter(phone_number=phone_number).delete()

        otp_code = str(random.randint(100000, 999999))

        pending = PendingRegistration(
            phone_number=phone_number,
            full_name=data["full_name"],
            password_hash=data["password"],  # প্লেইন পাসওয়ার্ড রাখছেন (make_password বাদ দিন)
            role=data.get("role", User.Role.CITIZEN),
            district=data.get("district"),
            email=data.get("email")
        )
        pending.set_otp(otp_code, validity_minutes=5)
        pending.save()

        send_sms(phone_number, otp_code)

        return Response({
            "status": True,
            "message": "Verification code sent to your phone number.",
            "verification_id": str(pending.verification_id)
        }, status=status.HTTP_200_OK)

class RegisterVerifyView(APIView):
    permission_classes = []
    def post(self, request):
        serializer = RegisterVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        verification_id = serializer.validated_data["verification_id"]
        input_otp = serializer.validated_data["otp"]

        try:
            pending = PendingRegistration.objects.get(verification_id=verification_id)
        except PendingRegistration.DoesNotExist:
            return Response({"status": False, "message": "Invalid or expired verification session."}, status=status.HTTP_400_BAD_REQUEST)

        # Expiration Check
        if pending.is_expired():
            pending.delete()
            return Response({"status": False, "message": "OTP has expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)

        # Max Attempts Check
        if pending.attempts >= pending.max_attempts:
            pending.delete()
            return Response({"status": False, "message": "Too many failed attempts. Registration session terminated."}, status=status.HTTP_400_BAD_REQUEST)

        # Hash Match Check
        if pending.otp_hash != PendingRegistration.hash_otp(input_otp):
            pending.attempts += 1
            pending.save(update_fields=["attempts"])
            return Response({"status": False, "message": f"Invalid OTP. Remaining attempts: {pending.max_attempts - pending.attempts}"}, status=status.HTTP_400_BAD_REQUEST)

        # Check phone unique constraint again before creating user
        if User.objects.filter(phone_number=pending.phone_number).exists():
            pending.delete()
            return Response({"status": False, "message": "Phone number is already registered."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            phone_number=pending.phone_number,
            full_name=pending.full_name,
            password=pending.password_hash,
            role=pending.role,
            district=pending.district,
            email=pending.email
        )
        # Auto Create Profile according to Role
        create_role_profile(user)
        # Remove temporary pending record
        pending.delete()

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        response = Response({
            "status": True,
            "message": "Registration verified successfully.",
            "user": {
                "id": user.id,
                "phone_number": user.phone_number,
                "full_name": user.full_name,
                "role": user.role
            },
            "token": access_token,
            "refresh_token": refresh_token
        }, status=status.HTTP_201_CREATED)

        # HTTP-Only Cookie for Refresh Token
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            secure=True,
            httponly=True,
            max_age=30 * 24 * 60 * 60,
            samesite="strict"
        )

        return response



class RegisterResendView(APIView):
    permission_classes = []
    def post(self, request):
        serializer = RegisterResendSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        verification_id = serializer.validated_data["verification_id"]

        try:
            pending = PendingRegistration.objects.get(verification_id=verification_id)
        except PendingRegistration.DoesNotExist:
            return Response({"status": False, "message": "Invalid verification session."}, status=status.HTTP_400_BAD_REQUEST)

        time_since_last_otp = (timezone.now() - pending.last_otp_sent_at).total_seconds()
        if time_since_last_otp < 60:
            remaining_time = int(60 - time_since_last_otp)
            return Response({
                "status": False,
                "message": f"Please wait {remaining_time} seconds before requesting a new OTP."
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        new_otp = str(random.randint(100000, 999999))
        pending.set_otp(new_otp, validity_minutes=5)
        pending.save()

        send_sms(pending.phone_number, new_otp)

        return Response({
            "status": True,
            "message": "A new verification code has been sent."
        }, status=status.HTTP_200_OK)


class UserLoginView(APIView):
    def post(self, request):
        try:
            username = request.data['username']
            password = request.data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                refresh = RefreshToken.for_user(user)
                response = Response(
                    {
                        "status": True,
                        "message": "Log in successfull.",
                        "full_name": user.full_name,
                        "token": str(refresh.access_token),
                        "refresh_token": str(refresh)
                    }, status=status.HTTP_200_OK
                )

                refresh_token = str(refresh)

                response.set_cookie(
                    key="refresh_token",
                    value=refresh_token,
                    secure=True,
                    httponly=True,
                    max_age=30 * 24 * 60 * 60,
                    samesite="strict"
                )

                return response

            else:
                return Response({'error': 'Invalid Credentials'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)



class UserLogoutView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        try:
            refreshToken = request.COOKIES.get("refresh_token")
            if not refreshToken:
                return Response(
                    {
                        "status": False,
                        "message": "Refresh Token required."
                    }, status=status.HTTP_400_BAD_REQUEST
                )
            token = RefreshToken(refreshToken)
            token.blacklist()

            response = Response(
                {
                    "status": True,
                    "message": "Log-Out succesfully."
                },
                status=status.HTTP_200_OK
            )

            response.delete_cookie("refresh_token")

            return response

        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": "An error occured while log out."
                }, status=status.HTTP_400_BAD_REQUEST
            )



# implement later in the frontend
class ForgetPasswordView(APIView):
    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response(
                {
                    "success" : False,
                    "message" : "Email is required."
                }
            )

        try:
            user = User.objects.get(email=email)
            otp = str(random.randint(100000, 999999))
            user.otp = otp
            user.save()

            html = send_otp_template(
                otp_code=otp
            )

            send_email(
                to_email=email,
                subject="OTP for registration",
                html=html
            )
            print(otp)
            response =  Response(
                {
                    "success" : True,
                    "message" : "Your Otp code sent to your email successfully.",
                }, status=status.HTTP_200_OK
            )

            response.set_cookie(
                key="email",
                value=email,
                secure=True,
                httponly=True,
                max_age= 5*60,
                samesite="strict"
            )

            return response
        except Exception as e:
            return Response(
                {
                    "success" : False,
                    "message" : "Email address is not Found."
                }, status=status.HTTP_404_NOT_FOUND
            )


class VerifyPasswordResetOTPAPIView(APIView):
    def post(self, request):

        email = request.COOKIES.get("email")
        otp = request.data.get("otp")
        print(email)

        if not email or not otp:
            return Response(
                {
                    "status": False,
                    "message": "email and OTP are required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.get(email=email)
        if not user:
            return Response(
                {
                    "status": False,
                    "message": "Invalid OTP."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.otp or not user.otp_created_at:
            return Response(
                {
                    "status": False,
                    "message": "Invalid or expired OTP."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        expiry_time = user.otp_created_at + timedelta(minutes=5)

        if timezone.now() > expiry_time:
            user.otp = None
            user.otp_created_at = None
            user.save(update_fields=["otp", "otp_created_at"])

            return Response(
                {
                    "status": False,
                    "message": "OTP has expired."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if user.otp != otp:
            return Response(
                {
                    "status": False,
                    "message": "Invalid OTP."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {
                "status": True,
                "message": "OTP verified successfully."
            },
            status=status.HTTP_200_OK
        )


class ResetPasswordAPIView(APIView):
    def post(self, request):

        email = request.COOKIES.get("email")
        new_password = request.data.get("new_password")
        confirm_password = request.data.get("confirm_password")

        if not all([
            email,
            new_password,
            confirm_password
        ]):
            return Response(
                {
                    "status": False,
                    "message": "All fields are required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_password != confirm_password:
            return Response(
                {
                    "status": False,
                    "message": "Passwords do not match."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.get(email=email)

        if not user:
            return Response(
                {
                    "status": False,
                    "message": "Invalid request."
                },
                status=status.HTTP_400_BAD_REQUEST
            )



        expiry_time = user.otp_created_at + timedelta(minutes=5)
        if timezone.now() > expiry_time:
            user.otp = None
            user.otp_created_at = None
            user.save(update_fields=["otp", "otp_created_at"])

            return Response(
                {
                    "status": False,
                    "message": "OTP has expired."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.otp = None
        user.otp_created_at = None

        user.save(
            update_fields=[
                "password",
                "otp",
                "otp_created_at"
            ]
        )

        return Response(
            {
                "status": True,
                "message": "Password reset successfully."
            },
            status=status.HTTP_200_OK
        )



class UserInfoView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        user = request.user

        if user.role == "CITIZEN":
            profile = CitizenProfile.objects.get(user=user)
            serializer = CitizenProfileSerializer(profile)

        elif user.role == "COMMUNITY_VOLUNTEER":
            profile = CommunityVolunteerProfile.objects.get(user=user)
            serializer = CommunityVolunteerProfileSerializer(profile)

        elif user.role == "RESPONDER":
            profile = ResponderProfile.objects.get(user=user)
            serializer = ResponderProfileSerializer(profile)

        elif user.role == "LOCAL_AUTHORITY":
            profile = LocalAuthorityProfile.objects.get(user=user)
            serializer = LocalAuthorityProfileSerializer(profile)

        elif user.role == "DISASTER_MANAGEMENT_OFFICER":
            profile = DisasterManagementOfficerProfile.objects.get(user=user)
            serializer = DisasterManagementOfficerProfileSerializer(profile)

        elif user.role == "SYSTEM_ADMINISTRATOR":
            profile = SystemAdministratorProfile.objects.get(user=user)
            serializer = SystemAdministratorProfileSerializer(profile)

        else:
            return Response(
                {
                    "status": False,
                    "message": "Invalid user role."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {
                "status": True,
                "message": "Profile fetched successfully.",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )

    def patch(self, request):
        user = request.user
        data = request.data

        user_serializer = UserUpdateSerializer(user, data=data, partial=True)
        if user_serializer.is_valid():
            user_serializer.save()
        else:
            return Response(
                {
                    "status": False,
                    "message": "User update failed.",
                    "errors": user_serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if user.role == "CITIZEN":
                profile = CitizenProfile.objects.get(user=user)
                profile_serializer = CitizenProfileUpdateSerializer(
                    profile, data=data, partial=True
                )

            elif user.role == "COMMUNITY_VOLUNTEER":
                profile = CommunityVolunteerProfile.objects.get(user=user)
                profile_serializer = CommunityVolunteerProfileUpdateSerializer(
                    profile, data=data, partial=True
                )

            elif user.role == "RESPONDER":
                profile = ResponderProfile.objects.get(user=user)
                profile_serializer = ResponderProfileUpdateSerializer(
                    profile, data=data, partial=True
                )

            elif user.role == "LOCAL_AUTHORITY":
                profile = LocalAuthorityProfile.objects.get(user=user)
                profile_serializer = LocalAuthorityProfileUpdateSerializer(
                    profile, data=data, partial=True
                )

            elif user.role == "DISASTER_MANAGEMENT_OFFICER":
                profile = DisasterManagementOfficerProfile.objects.get(user=user)
                profile_serializer = DisasterManagementOfficerProfileUpdateSerializer(
                    profile, data=data, partial=True
                )

            elif user.role == "SYSTEM_ADMINISTRATOR":
                profile = SystemAdministratorProfile.objects.get(user=user)
                profile_serializer = SystemAdministratorProfileUpdateSerializer(
                    profile, data=data, partial=True
                )

            else:
                return Response(
                    {
                        "status": False,
                        "message": "Invalid user role."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            if profile_serializer.is_valid():
                profile_serializer.save()
            else:
                return Response(
                    {
                        "status": False,
                        "message": "Profile update failed.",
                        "errors": profile_serializer.errors
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        except (CitizenProfile.DoesNotExist,
                CommunityVolunteerProfile.DoesNotExist,
                ResponderProfile.DoesNotExist,
                LocalAuthorityProfile.DoesNotExist,
                DisasterManagementOfficerProfile.DoesNotExist,
                SystemAdministratorProfile.DoesNotExist) as e:
            return Response(
                {
                    "status": False,
                    "message": f"Profile not found for this user role."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # Return the updated profile
        return self.get(request)


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        serializer = ProfileUserSerializer(user)

        return Response(
            {
                "status": True,
                "message": "Profile fetched successfully.",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )

    def patch(self, request):
        user = request.user
        data = request.data

        serializer = UserUpdateSerializer(user, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Profile updated successfully.",
                    "data": serializer.data
                },
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {
                    "status": False,
                    "message": "Profile update failed.",
                    "errors": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
