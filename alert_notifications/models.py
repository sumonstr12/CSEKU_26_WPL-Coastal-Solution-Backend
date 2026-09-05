from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()
from incidents.models import *


# Create your models here.

class Alert(models.Model):
    """
    Official disaster / emergency alerts.
    """

    ALERT_TYPES = (
        ("cyclone", "Cyclone Warning"),
        ("storm_surge", "Storm Surge Warning"),
        ("flood", "Flood Warning"),
        ("erosion", "Erosion Warning"),
        ("general", "General Alert"),
        ("emergency", "Emergency Alert"),
        ("preparedness", "Preparedness Instruction"),
        ("evacuation", "Evacuation Order"),
    )

    SEVERITY_CHOICES = (
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    )

    title = models.CharField(
        max_length=255,
    )

    title_bn = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    content = models.TextField()

    content_bn = models.TextField(
        blank=True,
        null=True,
    )

    alert_type = models.CharField(
        max_length=20,
        choices=ALERT_TYPES,
        default="general",
    )

    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default="medium",
    )

    affected_districts = models.JSONField(
        default=list,
        blank=True,
    )

    affected_upazilas = models.JSONField(
        default=list,
        blank=True,
    )

    geofence = models.JSONField(
        default=dict,
        blank=True,
    )

    valid_from = models.DateTimeField(
        default=timezone.now,
    )

    valid_until = models.DateTimeField(
        blank=True,
        null=True,
    )

    published_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="published_alerts",
    )

    published_at = models.DateTimeField(
        default=timezone.now,
    )

    is_active = models.BooleanField(
        default=True,
    )

    is_verified = models.BooleanField(
        default=False,
    )

    recommended_actions = models.JSONField(
        default=list,
        blank=True,
    )

    contact_info = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "alerts"

        indexes = [
            models.Index(
                fields=["alert_type", "severity"]
            ),
            models.Index(
                fields=["valid_from", "valid_until"]
            ),
            models.Index(
                fields=["is_active", "published_at"]
            ),
        ]

        ordering = ["-published_at"]

    def __str__(self):
        return self.title

    @property
    def is_valid(self):
        now = timezone.now()

        return (
            self.is_active
            and self.is_verified
            and self.valid_from <= now
            and (
                self.valid_until is None
                or now <= self.valid_until
            )
        )


class NotificationLog(models.Model):
    """
    Notification delivery history.
    """

    NOTIFICATION_TYPES = (
        ("report_submission", "Report Submission"),
        ("report_update", "Report Update"),
        ("alert", "New Alert"),
        ("critical_alert", "Critical Alert"),
        ("assignment", "Incident Assignment"),
        ("reminder", "Reminder"),
        ("broadcast", "Broadcast"),
    )

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
        ("read", "Read"),
    )

    recipient = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="notification_logs",
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPES,
    )

    subject = models.CharField(
        max_length=255,
    )

    body = models.TextField()

    body_bn = models.TextField(
        blank=True,
        null=True,
    )

    channels = models.JSONField(
        default=list,
        help_text="email, sms, push, in-app",
    )

    incident = models.ForeignKey(
        IncidentReport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_logs",
    )

    alert = models.ForeignKey(
        Alert,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_logs",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    error_message = models.TextField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    sent_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    read_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    class Meta:
        db_table = "notification_logs"

        indexes = [
            models.Index(
                fields=["recipient", "created_at"]
            ),
            models.Index(
                fields=["status", "notification_type"]
            ),
        ]

        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Notification to {self.recipient} "
            f"- {self.notification_type}"
        )
