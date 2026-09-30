import logging

from django.contrib.auth import get_user_model
from users.models import *
User = get_user_model()
logger = logging.getLogger(__name__)

REGISTRATION_DISTRICT_NAMES = {
    "সাতক্ষীরা": "Satkhira",
    "খুলনা": "Khulna",
    "বাগেরহাট": "Bagerhat",
    "পিরোজপুর": "Pirojpur",
    "বরগুনা": "Barguna",
    "পটুয়াখালী": "Patuakhali",
    "ভোলা": "Bhola",
    "লক্ষ্মীপুর": "Lakshmipur",
    "নোয়াখালী": "Noakhali",
    "কক্সবাজার": "Cox's Bazar",
    "চট্টগ্রাম": "Chattogram",
}


def send_sms(phone_number, otp):
    print(f"--- [SMS SENT] To: {phone_number} | OTP: {otp} ---")

def create_role_profile(user):
    if user.role == User.Role.CITIZEN:
        CitizenProfile.objects.get_or_create(user=user)
    elif user.role == User.Role.COMMUNITY_VOLUNTEER:
        district_name = REGISTRATION_DISTRICT_NAMES.get(user.district, user.district)
        administrative_area = AdministrativeArea.objects.filter(
            name=district_name,
            area_type=AdministrativeArea.AreaType.DISTRICT,
        ).first() if district_name else None
        if administrative_area is None:
            logger.warning(
                "No district AdministrativeArea found for community volunteer user_id=%s district=%r",
                user.pk,
                user.district,
            )
        profile, _ = CommunityVolunteerProfile.objects.get_or_create(user=user)
        if administrative_area and profile.administrative_area_id is None:
            profile.administrative_area = administrative_area
            profile.save(update_fields=["administrative_area", "updated_at"])
    elif user.role == User.Role.RESPONDER:
        ResponderProfile.objects.get_or_create(user=user, responder_type="EMERGENCY_RESPONDER")
    elif user.role == User.Role.LOCAL_AUTHORITY:
        LocalAuthorityProfile.objects.get_or_create(user=user, organization="N/A", designation="N/A")
    elif user.role == User.Role.DISASTER_MANAGEMENT_OFFICER:
        DisasterManagementOfficerProfile.objects.get_or_create(user=user, organization="N/A", designation="N/A")
    elif user.role == User.Role.SYSTEM_ADMINISTRATOR:
        SystemAdministratorProfile.objects.get_or_create(user=user)