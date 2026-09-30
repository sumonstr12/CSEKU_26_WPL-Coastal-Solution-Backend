from django.contrib.auth import get_user_model
from users.models import *
User = get_user_model()

def send_sms(phone_number, otp):
    print(f"--- [SMS SENT] To: {phone_number} | OTP: {otp} ---")

def create_role_profile(user):
    if user.role == User.Role.CITIZEN:
        CitizenProfile.objects.get_or_create(user=user)
    elif user.role == User.Role.COMMUNITY_VOLUNTEER:
        CommunityVolunteerProfile.objects.get_or_create(user=user)
    elif user.role == User.Role.RESPONDER:
        ResponderProfile.objects.get_or_create(user=user, responder_type="EMERGENCY_RESPONDER")
    elif user.role == User.Role.LOCAL_AUTHORITY:
        LocalAuthorityProfile.objects.get_or_create(user=user, organization="N/A", designation="N/A")
    elif user.role == User.Role.DISASTER_MANAGEMENT_OFFICER:
        DisasterManagementOfficerProfile.objects.get_or_create(user=user, organization="N/A", designation="N/A")
    elif user.role == User.Role.SYSTEM_ADMINISTRATOR:
        SystemAdministratorProfile.objects.get_or_create(user=user)