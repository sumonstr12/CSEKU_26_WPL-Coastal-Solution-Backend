"""
Profile serializers shaped for the Profiles UI.

Response / request shape matches frontend seed data + ProfileEditModal payload:

{
  "id": ...,
  "username": ...,
  "full_name": ...,
  "phone_number": ...,
  "email": ...,
  "role": ...,
  "date_of_birth": "YYYY-MM-DD" | null,
  "district": ...,
  "address": ... | null,
  "date_joined": ...,
  "last_login": ...,
  "account_status": "ACTIVE" | "INACTIVE",
  "profile": {
    "organization": ...,
    "designation": ...,
    "responder_type": ...,
    "availability_status": ...,
    "administrative_area": { "division", "district", "upazila", "union" } | null,
    "administrative_areas": [ {...}, ... ]
  }
}
"""

from rest_framework import serializers
from users.models import (
    User,
    AdministrativeArea,
    CitizenProfile,
    CommunityVolunteerProfile,
    ResponderProfile,
    LocalAuthorityProfile,
    DisasterManagementOfficerProfile,
    SystemAdministratorProfile,
)


# ---------------------------------------------------------------------------
# Helpers — AdministrativeArea tree → UI nested object
# ---------------------------------------------------------------------------

def area_to_nested(area):
    """
    Walk parent chain and return {division, district, upazila, union}.
    Missing levels are omitted.
    """
    if area is None:
        return None

    levels = {
        "DIVISION": None,
        "DISTRICT": None,
        "UPAZILA": None,
        "UNION": None,
    }
    current = area
    while current is not None:
        levels[current.area_type] = current.name
        current = current.parent

    result = {
        "division": levels["DIVISION"],
        "district": levels["DISTRICT"],
        "upazila": levels["UPAZILA"],
        "union": levels["UNION"],
    }
    return {k: v for k, v in result.items() if v is not None} or None


def nested_to_area(nested):
    """
    Resolve a UI nested area dict back to an AdministrativeArea instance.
    Prefers the most specific level (union > upazila > district > division).
    """
    if not nested or not isinstance(nested, dict):
        return None

    order = [
        ("union", "UNION"),
        ("upazila", "UPAZILA"),
        ("district", "DISTRICT"),
        ("division", "DIVISION"),
    ]
    for key, area_type in order:
        name = nested.get(key)
        if not name:
            continue
        qs = AdministrativeArea.objects.filter(name=name, area_type=area_type)
        parent_name = None
        parent_type = None
        if area_type == "UNION":
            parent_name, parent_type = nested.get("upazila"), "UPAZILA"
        elif area_type == "UPAZILA":
            parent_name, parent_type = nested.get("district"), "DISTRICT"
        elif area_type == "DISTRICT":
            parent_name, parent_type = nested.get("division"), "DIVISION"

        if parent_name and parent_type:
            parent = AdministrativeArea.objects.filter(
                name=parent_name, area_type=parent_type
            ).first()
            if parent:
                match = qs.filter(parent=parent).first()
                if match:
                    return match
        match = qs.first()
        if match:
            return match
    return None


def nested_list_to_areas(nested_list):
    if not nested_list:
        return []
    areas = []
    for item in nested_list:
        area = nested_to_area(item)
        if area and area not in areas:
            areas.append(area)
    return areas


# ---------------------------------------------------------------------------
# Read serializer
# ---------------------------------------------------------------------------

class ProfileReadSerializer(serializers.Serializer):
    """Builds the exact object the Profiles UI expects."""

    def to_representation(self, user):
        role = user.role
        profile_data = {}
        address = None

        try:
            if role == User.Role.CITIZEN:
                p = user.citizen_profile
                address = p.address
                profile_data["administrative_area"] = area_to_nested(
                    p.administrative_area
                )

            elif role == User.Role.COMMUNITY_VOLUNTEER:
                p = user.volunteer_profile
                profile_data["organization"] = p.organization
                profile_data["availability_status"] = p.availability_status
                profile_data["administrative_area"] = area_to_nested(
                    p.administrative_area
                )

            elif role == User.Role.RESPONDER:
                p = user.responder_profile
                profile_data["responder_type"] = p.responder_type
                profile_data["organization"] = p.organization
                profile_data["availability_status"] = p.availability_status
                profile_data["administrative_areas"] = [
                    area_to_nested(a)
                    for a in p.administrative_areas.all()
                    if area_to_nested(a)
                ]

            elif role == User.Role.LOCAL_AUTHORITY:
                p = user.authority_profile
                profile_data["organization"] = p.organization
                profile_data["designation"] = p.designation
                profile_data["administrative_area"] = area_to_nested(
                    p.administrative_area
                )

            elif role == User.Role.DISASTER_MANAGEMENT_OFFICER:
                p = user.disaster_management_profile
                profile_data["organization"] = p.organization
                profile_data["designation"] = p.designation
                profile_data["administrative_area"] = area_to_nested(
                    p.administrative_area
                )

            elif role == User.Role.SYSTEM_ADMINISTRATOR:
                p = user.admin_profile
                profile_data["designation"] = p.designation

        except Exception:
            pass

        return {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "email": user.email,
            "role": user.role,
            "date_of_birth": (
                user.date_of_birth.isoformat() if user.date_of_birth else None
            ),
            "district": user.district,
            "address": address,
            "date_joined": (
                user.date_joined.isoformat() if user.date_joined else None
            ),
            "last_login": (
                user.last_login.isoformat() if user.last_login else None
            ),
            "account_status": "ACTIVE" if user.is_active else "INACTIVE",
            "profile": profile_data,
        }


# ---------------------------------------------------------------------------
# Write / update serializer
# ---------------------------------------------------------------------------

class ProfileUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255, required=False)
    email = serializers.EmailField(
        required=False, allow_null=True, allow_blank=True
    )
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    district = serializers.CharField(
        max_length=100, required=False, allow_null=True, allow_blank=True
    )
    address = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    profile = serializers.DictField(required=False)

    def validate_email(self, value):
        if value in ("", None):
            return None
        user = self.context["request"].user
        if User.objects.exclude(pk=user.pk).filter(email=value).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )
        return value

    def validate_full_name(self, value):
        if value is not None and not str(value).strip():
            raise serializers.ValidationError("Full name cannot be empty.")
        return value.strip() if value else value

    def update(self, user, validated_data):
        for field in ("full_name", "email", "date_of_birth", "district"):
            if field in validated_data:
                setattr(user, field, validated_data[field])
        user.save()

        profile_payload = validated_data.get("profile") or {}
        address = validated_data.get("address")
        role = user.role

        if role == User.Role.CITIZEN:
            p, _ = CitizenProfile.objects.get_or_create(user=user)
            if address is not None:
                p.address = address or None
            if "administrative_area" in profile_payload:
                p.administrative_area = nested_to_area(
                    profile_payload["administrative_area"]
                )
            p.save()

        elif role == User.Role.COMMUNITY_VOLUNTEER:
            p, _ = CommunityVolunteerProfile.objects.get_or_create(user=user)
            if "organization" in profile_payload:
                p.organization = profile_payload["organization"] or None
            if "availability_status" in profile_payload:
                p.availability_status = (
                    profile_payload["availability_status"]
                    or p.availability_status
                )
            if "administrative_area" in profile_payload:
                p.administrative_area = nested_to_area(
                    profile_payload["administrative_area"]
                )
            p.save()

        elif role == User.Role.RESPONDER:
            p, _ = ResponderProfile.objects.get_or_create(
                user=user,
                defaults={
                    "responder_type": ResponderProfile.ResponderType.FIELD_OFFICER
                },
            )
            if (
                "responder_type" in profile_payload
                and profile_payload["responder_type"]
            ):
                p.responder_type = profile_payload["responder_type"]
            if "organization" in profile_payload:
                p.organization = profile_payload["organization"] or None
            if "availability_status" in profile_payload:
                p.availability_status = (
                    profile_payload["availability_status"]
                    or p.availability_status
                )
            p.save()
            if "administrative_areas" in profile_payload:
                areas = nested_list_to_areas(
                    profile_payload["administrative_areas"]
                )
                p.administrative_areas.set(areas)

        elif role == User.Role.LOCAL_AUTHORITY:
            p, _ = LocalAuthorityProfile.objects.get_or_create(
                user=user,
                defaults={"organization": "", "designation": ""},
            )
            if "organization" in profile_payload:
                p.organization = profile_payload["organization"] or None
            if "designation" in profile_payload:
                p.designation = profile_payload["designation"] or None
            if "administrative_area" in profile_payload:
                p.administrative_area = nested_to_area(
                    profile_payload["administrative_area"]
                )
            p.save()

        elif role == User.Role.DISASTER_MANAGEMENT_OFFICER:
            p, _ = DisasterManagementOfficerProfile.objects.get_or_create(
                user=user,
                defaults={"organization": "", "designation": ""},
            )
            if "organization" in profile_payload:
                p.organization = profile_payload["organization"] or None
            if "designation" in profile_payload:
                p.designation = profile_payload["designation"] or None
            if "administrative_area" in profile_payload:
                p.administrative_area = nested_to_area(
                    profile_payload["administrative_area"]
                )
            p.save()

        elif role == User.Role.SYSTEM_ADMINISTRATOR:
            p, _ = SystemAdministratorProfile.objects.get_or_create(user=user)
            if "designation" in profile_payload:
                p.designation = profile_payload["designation"] or None
            p.save()

        return user