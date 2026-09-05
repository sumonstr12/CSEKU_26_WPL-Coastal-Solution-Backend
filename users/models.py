
import uuid
import hashlib
import random
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser, BaseUserManager, PermissionsMixin, UserManager
)
from datetime import timedelta
from django.utils import timezone


# Create your models here.

class PendingRegistration(models.Model):
    verification_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    phone_number = models.CharField(max_length=20, db_index=True)
    full_name = models.CharField(max_length=255)
    password_hash = models.CharField(max_length=255)  # Django encrypted password
    role = models.CharField(max_length=50, default="CITIZEN")
    email = models.EmailField(null=True, blank=True)
    district = models.CharField(max_length=100, blank=True, null=True)

    otp_hash = models.CharField(max_length=255)
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=5)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_otp_sent_at = models.DateTimeField(auto_now=True)

    def is_expired(self):
        return timezone.now() > self.expires_at

    @staticmethod
    def hash_otp(otp_code: str) -> str:
        return hashlib.sha256(otp_code.encode('utf-8')).hexdigest()

    def set_otp(self, otp_code: str, validity_minutes=5):
        self.otp_hash = self.hash_otp(otp_code)
        self.expires_at = timezone.now() + timedelta(minutes=validity_minutes)
        self.last_otp_sent_at = timezone.now()
        self.attempts = 0


class UserManager(BaseUserManager):
    def generate_unique_username(self):
        while True:
            candidate_username = f"cs_{random.randint(10000, 99999)}"
            if not self.filter(username=candidate_username).exists():
                return candidate_username

    def create_user(self, phone_number, username=None, email=None, password=None, **extra_fields):
        if not phone_number:
            raise ValueError("User must have phone_number")

        if not username:
            username = self.generate_unique_username()

        if email:
            email = self.normalize_email(email)
        user = self.model(
            phone_number=phone_number,
            username=username,
            email=email,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, username=None, email=None, password=None, **extra_fields):

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
            phone_number=phone_number,
            username=username,
            email=email,
            password=password,
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
    email = models.EmailField(max_length=255, unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=255, unique=True)
    role = models.CharField(
        max_length=255,
        choices=Role.choices,
        default=Role.CITIZEN,
    )
    date_of_birth = models.DateField(null=True, blank=True)
    district = models.CharField(max_length=100, blank=True, null=True)

    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(auto_now=True)
    updated_at = models.DateTimeField(auto_now=True)
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return f"{self.full_name} role {self.role}"

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

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
        unique_together = ("name", "area_type")

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
    administrative_areas = models.ManyToManyField(
        "AdministrativeArea",
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



