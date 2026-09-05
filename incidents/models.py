from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.utils import timezone
from users.models import *
from django.contrib.auth import get_user_model
User = get_user_model()



# ============================================================
# INCIDENT CATEGORY
# ============================================================

class IncidentCategory(models.Model):
    """
    Defines the type/category of disaster or incident.

    Examples:
        - Cyclone
        - Flood
        - Tidal Surge
        - River Erosion
        - Embankment Failure
        - Waterlogging
        - Storm Surge
        - Landslide
        - Fire
    """

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    name_bn = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    description_bn = models.TextField(
        blank=True,
        null=True,
    )

    icon = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Icon name or icon identifier used by frontend.",
    )

    color_code = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Optional UI color code such as #FF5733.",
    )

    PRIORITY_CHOICES = (
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    )

    default_priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default="medium",
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# ============================================================
# DAMAGE TYPE
# ============================================================

class DamageType(models.Model):
    """
    Normalized list of damages that can occur during an incident.

    Examples:
        - House Damage
        - Embankment Break
        - Road Submerged
        - Trees Uprooted
        - Crop Damage
        - Drinking Water Contamination
        - Electricity Outage
        - Communication Disruption
    """

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    name_bn = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# ============================================================
# INCIDENT REPORT
# ============================================================

class IncidentReport(models.Model):
    """
    Main entity representing a disaster/incident report
    submitted by a citizen, volunteer, authority, etc.
    """

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    STATUS_CHOICES = (
        ("submitted", "Submitted"),
        ("under_review", "Under Review"),
        ("verified", "Verified"),
        ("rejected", "Rejected"),
        ("duplicate", "Duplicate"),
        ("assigned", "Assigned"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="submitted",
        db_index=True,
    )

    # --------------------------------------------------------
    # PRIORITY
    # --------------------------------------------------------

    PRIORITY_CHOICES = (
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    )

    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default="medium",
        db_index=True,
    )

    # --------------------------------------------------------
    # SEVERITY
    # --------------------------------------------------------

    severity = models.PositiveSmallIntegerField(
        default=1,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5),
        ],
        help_text="Severity score from 1 (lowest) to 5 (highest).",
    )

    # --------------------------------------------------------
    # SITUATION
    # --------------------------------------------------------

    SITUATION_CHOICES = (
        ("worsening", "Worsening"),
        ("stable", "Stable"),
        ("improving", "Improving"),
    )

    situation = models.CharField(
        max_length=20,
        choices=SITUATION_CHOICES,
        default="stable",
        db_index=True,
    )

    # --------------------------------------------------------
    # BASIC INFORMATION
    # --------------------------------------------------------

    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    title_bn = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    description = models.TextField()

    description_bn = models.TextField(
        blank=True,
        null=True,
    )

    category = models.ForeignKey(
        IncidentCategory,
        on_delete=models.PROTECT,
        related_name="incidents",
    )

    # --------------------------------------------------------
    # DAMAGE INFORMATION
    # --------------------------------------------------------

    damage_types = models.ManyToManyField(
        DamageType,
        blank=True,
        related_name="incidents",
    )

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    LOCATION_SOURCE_CHOICES = (
        ("gps", "GPS"),
        ("manual", "Manual"),
        ("network", "Network"),
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
    )

    location_accuracy = models.FloatField(
        blank=True,
        null=True,
        help_text="GPS accuracy in meters.",
    )

    location_source = models.CharField(
        max_length=20,
        choices=LOCATION_SOURCE_CHOICES,
        default="manual",
    )

    address = models.TextField(
        blank=True,
        null=True,
    )

    village = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    union = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    upazila = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    district = models.CharField(
        max_length=150,
        db_index=True,
    )

    division = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # REPORTER
    # --------------------------------------------------------

    reporter = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="incident_reports",
        blank=True,
        null=True,
    )

    # this use only for if user is_annomous
    reporter_name = models.CharField(max_length=255, blank=True, null=True)
    reporter_phone = models.CharField(max_length=15, blank=True, null=True)

    is_anonymous = models.BooleanField(
        default=False,
    )

    # --------------------------------------------------------
    # TIME INFORMATION
    # --------------------------------------------------------

    report_time = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    incident_time = models.DateTimeField(
        default=timezone.now,
    )

    # --------------------------------------------------------
    # AFFECTED PEOPLE
    # --------------------------------------------------------

    affected_people_estimate = models.PositiveIntegerField(
        default=0,
    )

    affected_families_estimate = models.PositiveIntegerField(
        default=0,
    )

    injuries_count = models.PositiveIntegerField(
        default=0,
    )

    fatalities_count = models.PositiveIntegerField(
        default=0,
    )

    property_damage_estimate = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Estimated property damage in BDT.",
    )

    # --------------------------------------------------------
    # SOS / URGENT RESCUE
    # --------------------------------------------------------

    is_sos = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when urgent rescue is requested.",
    )

    # --------------------------------------------------------
    # DUPLICATE REPORT
    # --------------------------------------------------------

    duplicate_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="duplicate_reports",
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # ADDITIONAL INFORMATION
    # --------------------------------------------------------

    additional_info = models.JSONField(
        default=dict,
        blank=True,
    )

    # --------------------------------------------------------
    # AUDIT
    # --------------------------------------------------------

    last_modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="modified_incident_reports",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    # --------------------------------------------------------
    # META
    # --------------------------------------------------------

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["status", "priority"]
            ),
            models.Index(
                fields=["latitude", "longitude"]
            ),
            models.Index(
                fields=["district", "upazila"]
            ),
            models.Index(
                fields=["category", "is_sos"]
            ),
            models.Index(
                fields=["created_at"]
            ),
            models.Index(
                fields=["situation"]
            ),
        ]

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    def clean(self):
        super().clean()

        # Latitude and longitude must appear together.
        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError(
                "Latitude and longitude must be provided together."
            )

        # Validate latitude range.
        if self.latitude is not None:
            if not -90 <= float(self.latitude) <= 90:
                raise ValidationError(
                    {"latitude": "Latitude must be between -90 and 90."}
                )

        # Validate longitude range.
        if self.longitude is not None:
            if not -180 <= float(self.longitude) <= 180:
                raise ValidationError(
                    {"longitude": "Longitude must be between -180 and 180."}
                )

        # Incident time cannot be in the future.
        if (
            self.incident_time
            and self.incident_time > timezone.now()
        ):
            raise ValidationError(
                {
                    "incident_time":
                    "Incident time cannot be in the future."
                }
            )

        # A report cannot be its own duplicate.
        if (
            self.pk
            and self.duplicate_of_id == self.pk
        ):
            raise ValidationError(
                {
                    "duplicate_of":
                    "An incident cannot be a duplicate of itself."
                }
            )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    def save(self, *args, **kwargs):
        # Automatically use category's default priority
        # when a new incident is created.
        if (
            not self.pk
            and self.category_id
            and self.priority == "medium"
        ):
            self.priority = self.category.default_priority

        self.full_clean()

        super().save(*args, **kwargs)

    # --------------------------------------------------------
    # HELPERS
    # --------------------------------------------------------

    def get_location_display(self):
        parts = [
            self.village,
            self.union,
            self.upazila,
            self.district,
            self.division,
        ]

        parts = [
            part for part in parts
            if part
        ]

        return ", ".join(parts)

    @property
    def is_verified(self):
        return self.status == "verified"

    @property
    def is_high_priority(self):
        return self.priority in [
            "critical",
            "high",
        ]

    def __str__(self):
        return (
            self.title
            or f"Incident #{self.pk}"
        )


# ============================================================
# EVIDENCE ATTACHMENT
# ============================================================

def evidence_upload_path(instance, filename):
    """
    Stores evidence files under:

        media/incidents/<incident_id>/<filename>
    """

    return (
        f"incidents/"
        f"{instance.incident_id}/"
        f"{filename}"
    )


class EvidenceAttachment(models.Model):
    """
    Stores photos, videos, audio, and documents
    related to an incident.
    """

    FILE_TYPE_CHOICES = (
        ("photo", "Photo"),
        ("video", "Video"),
        ("audio", "Audio"),
        ("document", "Document"),
    )

    incident = models.ForeignKey(
        IncidentReport,
        on_delete=models.CASCADE,
        related_name="evidence",
    )

    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="uploaded_evidence",
        blank=True,
        null=True,
    )

    file = models.FileField(
        upload_to=evidence_upload_path,
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "jpg",
                    "jpeg",
                    "png",
                    "webp",
                    "mp4",
                    "mov",
                    "avi",
                    "mp3",
                    "wav",
                    "pdf",
                    "doc",
                    "docx",
                ]
            )
        ],
    )

    file_name = models.CharField(
        max_length=255,
        blank=True,
    )

    file_size = models.PositiveBigIntegerField(
        default=0,
    )

    file_type = models.CharField(
        max_length=20,
        choices=FILE_TYPE_CHOICES,
    )

    mime_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    thumbnail = models.ImageField(
        upload_to="incidents/thumbnails/",
        blank=True,
        null=True,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    description_bn = models.TextField(
        blank=True,
        null=True,
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
    )

    is_verified = models.BooleanField(
        default=False,
    )

    is_public = models.BooleanField(
        default=True,
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-uploaded_at"]

        indexes = [
            models.Index(
                fields=["incident", "file_type"]
            ),
            models.Index(
                fields=["uploaded_at"]
            ),
        ]

    def clean(self):
        super().clean()

        if not self.file:
            return

        # File size limits:
        #
        # Photo/document/audio -> 20 MB
        # Video                -> 50 MB

        max_size = (
            50 * 1024 * 1024
            if self.file_type == "video"
            else 20 * 1024 * 1024
        )

        if self.file.size > max_size:
            raise ValidationError(
                {
                    "file":
                    f"File size cannot exceed "
                    f"{max_size // (1024 * 1024)} MB."
                }
            )

    def save(self, *args, **kwargs):
        if self.file:
            self.file_size = self.file.size

            if not self.file_name:
                self.file_name = self.file.name

        self.full_clean()

        super().save(*args, **kwargs)

    @property
    def file_size_mb(self):
        return round(
            self.file_size / (1024 * 1024),
            2
        )

    def __str__(self):
        return self.file_name or f"Evidence #{self.pk}"


# ============================================================
# VERIFICATION RECORD
# ============================================================

class VerificationRecord(models.Model):
    """
    Records verification/review performed by an
    authorized officer or system.
    """

    VERIFICATION_STATUS_CHOICES = (
        ("pending", "Pending"),
        ("verified", "Verified"),
        ("unverified", "Unverified"),
        ("rejected", "Rejected"),
        ("duplicate", "Duplicate"),
    )

    incident = models.ForeignKey(
        IncidentReport,
        on_delete=models.CASCADE,
        related_name="verification_records",
    )

    verifier = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="verification_records",
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default="pending",
    )

    priority_assigned = models.CharField(
        max_length=20,
        choices=IncidentReport.PRIORITY_CHOICES,
        blank=True,
        null=True,
    )

    severity_assigned = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5),
        ],
    )

    comments = models.TextField(
        blank=True,
        null=True,
    )

    comments_bn = models.TextField(
        blank=True,
        null=True,
    )

    internal_notes = models.TextField(
        blank=True,
        null=True,
    )

    affected_people_count = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    affected_families_count = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    injuries_count = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    fatalities_count = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    response_recommendation = models.TextField(
        blank=True,
        null=True,
    )

    recommended_response_team = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    verification_time = models.DateTimeField(
        default=timezone.now,
    )

    is_automated = models.BooleanField(
        default=False,
    )

    automation_confidence = models.FloatField(
        blank=True,
        null=True,
        validators=[
            MinValueValidator(0.0),
            MaxValueValidator(1.0),
        ],
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["incident", "status"]
            ),
            models.Index(
                fields=["verifier"]
            ),
        ]

    def clean(self):
        super().clean()

        if self.status == "verified":

            if not self.priority_assigned:
                raise ValidationError(
                    {
                        "priority_assigned":
                        "Priority is required when an incident is verified."
                    }
                )

            if self.severity_assigned is None:
                raise ValidationError(
                    {
                        "severity_assigned":
                        "Severity is required when an incident is verified."
                    }
                )

        if self.is_automated:
            if self.automation_confidence is None:
                raise ValidationError(
                    {
                        "automation_confidence":
                        "Automation confidence is required for automated verification."
                    }
                )

    def __str__(self):
        return (
            f"Verification #{self.pk} "
            f"- Incident #{self.incident_id}"
        )


# ============================================================
# TRIAGE LOG
# ============================================================

class TriageLog(models.Model):
    """
    Stores the history of triage decisions for an incident.
    """

    TRIAGE_RATING_CHOICES = (
        (1, "Very Low"),
        (2, "Low"),
        (3, "High"),
        (4, "Very High"),
    )

    verification = models.ForeignKey(
        VerificationRecord,
        on_delete=models.CASCADE,
        related_name="triage_logs",
    )

    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="triage_logs",
        blank=True,
        null=True,
    )

    category_assigned = models.ForeignKey(
        IncidentCategory,
        on_delete=models.SET_NULL,
        related_name="triage_logs",
        blank=True,
        null=True,
    )

    priority_before = models.CharField(
        max_length=20,
        choices=IncidentReport.PRIORITY_CHOICES,
        blank=True,
        null=True,
    )

    priority_after = models.CharField(
        max_length=20,
        choices=IncidentReport.PRIORITY_CHOICES,
    )

    triage_notes = models.TextField(
        blank=True,
        null=True,
    )

    triage_notes_bn = models.TextField(
        blank=True,
        null=True,
    )

    triage_rating = models.PositiveSmallIntegerField(
        choices=TRIAGE_RATING_CHOICES,
    )

    factors_considered = models.JSONField(
        default=list,
        blank=True,
    )

    estimated_response_time = models.DurationField(
        blank=True,
        null=True,
    )

    performed_at = models.DateTimeField(
        default=timezone.now,
    )

    class Meta:
        ordering = ["-performed_at"]

        indexes = [
            models.Index(
                fields=["verification", "performed_at"]
            ),
            models.Index(
                fields=["priority_after"]
            ),
        ]

    def __str__(self):
        return (
            f"Triage #{self.pk} "
            f"- Verification #{self.verification_id}"
        )


# ============================================================
# RESPONSE ASSIGNMENT
# ============================================================

class ResponseAssignment(models.Model):
    """
    Assigns a verified incident to a responder/team.
    """

    ASSIGNMENT_STATUS_CHOICES = (
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    )

    incident = models.ForeignKey(
        IncidentReport,
        on_delete=models.CASCADE,
        related_name="response_assignments",
    )

    assigned_to = models.ForeignKey(
        ResponderProfile,
        on_delete=models.CASCADE,
        related_name="response_assignments",
    )

    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="created_response_assignments",
        blank=True,
        null=True,
    )

    assignment_time = models.DateTimeField(
        default=timezone.now,
    )

    response_deadline = models.DateTimeField(
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=ASSIGNMENT_STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    instructions = models.TextField(
        blank=True,
        null=True,
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["incident", "status"]
            ),
            models.Index(
                fields=["assigned_to", "status"]
            ),
        ]

    def clean(self):
        super().clean()

        if (
            self.response_deadline
            and self.assignment_time
            and self.response_deadline < self.assignment_time
        ):
            raise ValidationError(
                {
                    "response_deadline":
                    "Response deadline cannot be earlier than assignment time."
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Assignment #{self.pk} "
            f"- Incident #{self.incident_id}"
        )


# ============================================================
# RESPONSE ACTION
# ============================================================

class ResponseAction(models.Model):
    """
    Records an individual action performed by a responder
    during disaster response.
    """

    ACTION_TYPE_CHOICES = (
        ("arrived", "Arrived at Location"),
        ("assessment", "Assessment"),
        ("rescue", "Rescue"),
        ("evacuation", "Evacuation"),
        ("medical", "Medical Assistance"),
        ("supply", "Supply Distribution"),
        ("communication", "Communication"),
        ("resolution", "Resolution"),
        ("escalation", "Escalation"),
        ("other", "Other"),
    )

    assignment = models.ForeignKey(
        ResponseAssignment,
        on_delete=models.CASCADE,
        related_name="response_actions",
    )

    performed_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="response_actions",
    )

    action_type = models.CharField(
        max_length=30,
        choices=ACTION_TYPE_CHOICES,
    )

    description = models.TextField()

    description_bn = models.TextField(
        blank=True,
        null=True,
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
    )

    resources_used = models.JSONField(
        default=list,
        blank=True,
    )

    personnel_count = models.PositiveIntegerField(
        default=1,
    )

    notes = models.JSONField(
        default=dict,
        blank=True,
    )

    action_time = models.DateTimeField(
        default=timezone.now,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-action_time"]

        indexes = [
            models.Index(
                fields=["assignment", "action_time"]
            ),
            models.Index(
                fields=["performed_by", "action_time"]
            ),
        ]

    def clean(self):
        super().clean()

        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError(
                "Latitude and longitude must be provided together."
            )

        if self.latitude is not None:
            if not -90 <= float(self.latitude) <= 90:
                raise ValidationError(
                    {
                        "latitude":
                        "Latitude must be between -90 and 90."
                    }
                )

        if self.longitude is not None:
            if not -180 <= float(self.longitude) <= 180:
                raise ValidationError(
                    {
                        "longitude":
                        "Longitude must be between -180 and 180."
                    }
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.action_type} "
            f"- Assignment #{self.assignment_id}"
        )