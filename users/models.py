from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser, BaseUserManager, PermissionsMixin, UserManager
)
from datetime import datetime, timezone
import uuid

# Create your models here.

class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not username:
            raise ValueError("Users must have a username")
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(
            username=username,
            email=email,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password, **extra_fields):

        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault(
            "role",
            User.Role.SYSTEM_ADMINISTRATOR
        )
        if extra_fields.get("is_staff") is not True:
            raise ValueError(
                "Superuser must have is_staff=True."
            )
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(
                "Superuser must have is_superuser=True."
            )
        return self.create_user(
            username,
            email,
            password,
            **extra_fields
        )


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CITIZEN = "CITIZEN", "Citizen"
        COMMUNITY_VOLUNTEER = "COMMUNITY_VOLUNTEER", "Community Volunteer"
        RESPONDER = "RESPONDER", "Responder"
        LOCAL_AUTHORITY = "LOCAL_AUTHORITY", "Local Authority"
        DISASTER_MANAGEMENT_OFFICER = (
            "DISASTER_MANAGEMENT_OFFICER",
            "Disaster Management Officer",
        )
        SYSTEM_ADMINISTRATOR = (
            "SYSTEM_ADMINISTRATOR",
            "System Administrator",
        )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    username = models.CharField(max_length=255, unique=True)
    full_name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, unique=True)
    phone_number = models.CharField(max_length=255)
    role = models.CharField(
        max_length=255,
        choices=Role.choices,
        default=Role.CITIZEN,
    )

    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(auto_now=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.full_name} role {self.role}"

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    objects = UserManager()


class AdministrativeArea(models.Model):
    class AreaType(models.TextChoices):
        DIVISION = "DIVISION", "Division"
        DISTRICT = "DISTRICT", "District"
        UPAZILA = "UPAZILA", "Upazila"
        UNION = "UNION", "Union"

    name = models.CharField(max_length=255)
    area_type = models.CharField(max_length=20, choices=AreaType.choices)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = ("name", "area_type", "parent")

    def __str__(self):
        return f"{self.name} ({self.get_area_type_display()})"


class SystemAdministratorProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="admin_profile"
    )
    designation = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.full_name

class DisasterManagementOfficerProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="disaster_management_profile"
    )
    organization = models.CharField(max_length=255)
    designation = models.CharField(max_length=255)

    administrative_area = models.ForeignKey(
        "AdministrativeArea",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disaster_management_officers"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.full_name


class LocalAuthorityProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="authority_profile"
    )
    organization = models.CharField(max_length=255)
    designation = models.CharField(max_length=255)
    administrative_area = models.ForeignKey(
        "AdministrativeArea",
        on_delete=models.SET_NULL,
        null=True,
        related_name="authorities"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ResponderProfile(models.Model):
    class ResponderType(models.TextChoices):
        FIELD_OFFICER = "FIELD_OFFICER", "Field Officer"
        RESCUE_TEAM = "RESCUE_TEAM", "Rescue Team"
        MEDICAL_RESPONDER = "MEDICAL_RESPONDER", "Medical Responder"
        EMERGENCY_RESPONDER = (
            "EMERGENCY_RESPONDER",
            "Emergency Responder"
        )
    class AvailabilityStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        ON_MISSION = "ON_MISSION", "On Mission"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="responder_profile"
    )
    responder_type = models.CharField(
        max_length=50,
        choices=ResponderType.choices
    )
    organization = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )
    administrative_area = models.ForeignKey(
        "AdministrativeArea",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responders"
    )
    availability_status = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.AVAILABLE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.full_name


class CommunityVolunteerProfile(models.Model):
    class AvailabilityStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        BUSY = "BUSY", "Busy"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="volunteer_profile"
    )
    organization = models.CharField(max_length=255, blank=True, null=True)

    administrative_area = models.ForeignKey(
        "AdministrativeArea",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="volunteers"
    )
    availability_status = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.AVAILABLE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.full_name

class CitizenProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="citizen_profile"
    )

    address = models.TextField(blank=True, null=True)
    administrative_area = models.ForeignKey(
        "AdministrativeArea",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="citizens"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.full_name} Role {self.user.role}"



