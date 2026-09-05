from django.core.exceptions import ValidationError
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from .models import *

class RegisterRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=6)
    full_name = serializers.CharField(max_length=255)
    role = serializers.ChoiceField(choices=User.Role.choices, default=User.Role.CITIZEN)
    district = serializers.CharField(max_length=100, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)

    def validate_phone_number(self, value):
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        return value


class RegisterVerifySerializer(serializers.Serializer):
    verification_id = serializers.UUIDField()
    otp = serializers.CharField(max_length=6, min_length=6)


class RegisterResendSerializer(serializers.Serializer):
    verification_id = serializers.UUIDField()

class AdministrativeAreaSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(
        source="parent.name",
        read_only=True
    )

    class Meta:
        model = AdministrativeArea
        fields = [
            "id",
            "name",
            "area_type",
            "parent",
            "parent_name",
            "created_at",
            "updated_at",
        ]


class ProfileUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "full_name",
            "email",
            "phone_number",
            "role",
            "date_of_birth",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "username",
            "role",
            "date_joined",
        ]



class CitizenProfileSerializer(serializers.ModelSerializer):
    user = ProfileUserSerializer(read_only=True)
    administrative_area_details = AdministrativeAreaSerializer(
        source="administrative_area",
        read_only=True
    )

    class Meta:
        model = CitizenProfile
        fields = [
            "id",
            "user",
            "address",
            "administrative_area",
            "administrative_area_details",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class CommunityVolunteerProfileSerializer(serializers.ModelSerializer):
    user = ProfileUserSerializer(read_only=True)
    administrative_area_details = AdministrativeAreaSerializer(
        source="administrative_area",
        read_only=True
    )

    class Meta:
        model = CommunityVolunteerProfile
        fields = [
            "id",
            "user",
            "organization",
            "administrative_area",
            "administrative_area_details",
            "availability_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class ResponderProfileSerializer(serializers.ModelSerializer):
    user = ProfileUserSerializer(read_only=True)
    administrative_area_details = AdministrativeAreaSerializer(
        source="administrative_area",
        read_only=True
    )

    class Meta:
        model = ResponderProfile
        fields = [
            "id",
            "user",
            "responder_type",
            "organization",
            "administrative_area",
            "administrative_area_details",
            "availability_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class LocalAuthorityProfileSerializer(serializers.ModelSerializer):
    user = ProfileUserSerializer(read_only=True)
    administrative_area_details = AdministrativeAreaSerializer(
        source="administrative_area",
        read_only=True
    )

    class Meta:
        model = LocalAuthorityProfile
        fields = [
            "id",
            "user",
            "organization",
            "designation",
            "administrative_area",
            "administrative_area_details",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class DisasterManagementOfficerProfileSerializer(
    serializers.ModelSerializer
):
    user = ProfileUserSerializer(read_only=True)
    administrative_area_details = AdministrativeAreaSerializer(
        source="administrative_area",
        read_only=True
    )

    class Meta:
        model = DisasterManagementOfficerProfile
        fields = [
            "id",
            "user",
            "organization",
            "designation",
            "administrative_area",
            "administrative_area_details",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class SystemAdministratorProfileSerializer(serializers.ModelSerializer):
    user = ProfileUserSerializer(read_only=True)

    class Meta:
        model = SystemAdministratorProfile
        fields = [
            "id",
            "user",
            "designation",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
        ]



# Update prodile and info
class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'full_name', 'email', 'phone_number', 'date_of_birth'
        ]
        extra_kwargs = {
            'email': {'required': False},
            'full_name': {'required': False},
            'phone_number': {'required': False},
            'date_of_birth': {'required': False}
        }

    def validate_email(self, value):
        if value:
            # Check if email is already taken by another user
            if User.objects.exclude(id=self.instance.id).filter(email=value).exists():
                raise serializers.ValidationError("A user with this email already exists.")
        return value


class CitizenProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CitizenProfile
        fields = ['address', 'administrative_area']
        extra_kwargs = {
            'address': {'required': False},
            'administrative_area': {'required': False}
        }


class CommunityVolunteerProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunityVolunteerProfile
        fields = ['organization', 'administrative_area', 'availability_status']
        extra_kwargs = {
            'organization': {'required': False},
            'administrative_area': {'required': False},
            'availability_status': {'required': False}
        }


class ResponderProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResponderProfile
        fields = ['responder_type', 'organization', 'administrative_area', 'availability_status']
        extra_kwargs = {
            'responder_type': {'required': False},
            'organization': {'required': False},
            'administrative_area': {'required': False},
            'availability_status': {'required': False}
        }


class LocalAuthorityProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocalAuthorityProfile
        fields = ['organization', 'designation', 'administrative_area']
        extra_kwargs = {
            'organization': {'required': False},
            'designation': {'required': False},
            'administrative_area': {'required': False}
        }


class DisasterManagementOfficerProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisasterManagementOfficerProfile
        fields = ['organization', 'designation', 'administrative_area']
        extra_kwargs = {
            'organization': {'required': False},
            'designation': {'required': False},
            'administrative_area': {'required': False}
        }


class SystemAdministratorProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemAdministratorProfile
        fields = ['designation']
        extra_kwargs = {
            'designation': {'required': False}
        }