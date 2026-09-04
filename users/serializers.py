from django.core.exceptions import ValidationError
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from .models import *

class UserRegistrationSerializer(ModelSerializer):
    class Meta:
        model = User
        fields = ["username","email","password","full_name","phone_number","role", "date_of_birth"]
        extra_kwargs = {
            "password": {"write_only": True},
            "date_of_birth": {"required": False, "allow_null": True}
        }

    def validate(self, data):
        role = data["role"]
        if role not in ["CITIZEN","COMMUNITY_VOLUNTEER", "RESPONDER", "LOCAL_AUTHORITY", "DISASTER_MANAGEMENT_OFFICER", "SYSTEM_ADMINISTRATOR"]:
            return serializers.ValidationError(f'Role {role} not valid. Choose valid one.')

        date_of_birth = data.get("date_of_birth")
        if role != "CITIZEN" and not date_of_birth:
            return serializers.ValidationError(f'Must be submit date of birth. Choose valid one.')

        return data


    def create(self, validated_data):

        password = validated_data.pop("password")

        user = User.objects.create_user(
            password=password,
            **validated_data
        )

        if user.role == User.Role.CITIZEN:
            CitizenProfile.objects.create(
                user=user
            )

        elif user.role == User.Role.COMMUNITY_VOLUNTEER:
            CommunityVolunteerProfile.objects.create(
                user=user
            )

        elif user.role == User.Role.RESPONDER:
            ResponderProfile.objects.create(
                user=user
            )

        elif user.role == User.Role.LOCAL_AUTHORITY:
            LocalAuthorityProfile.objects.create(
                user=user
            )

        elif user.role == User.Role.DISASTER_MANAGEMENT_OFFICER:
            DisasterManagementOfficerProfile.objects.create(
                user=user
            )

        elif user.role == User.Role.SYSTEM_ADMINISTRATOR:
            SystemAdministratorProfile.objects.create(
                user=user
            )

        return user

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