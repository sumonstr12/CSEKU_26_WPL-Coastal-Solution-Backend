from django.contrib.auth import get_user_model

from healper_functions import sms_service
from healper_functions.sms_service import send_otp_sms
from users.models import *
from .sms_service import send_otp_sms
User = get_user_model()

def send_sms(phone_number, otp):
    success = send_otp_sms(phone_number, otp)
    print(success)

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