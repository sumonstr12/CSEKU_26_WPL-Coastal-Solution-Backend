from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
User = get_user_model()

class ResponderAvailabilityLog(models.Model):
    """একজন responder কখন availability বদলেছে — ড্যাশবোর্ডের হিস্ট্রি।"""

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        ON_MISSION = "ON_MISSION", "On Mission"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="responder_availability_logs",
    )
    status = models.CharField(max_length=20, choices=Status.choices)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id} → {self.status}"


class VolunteerActivity(models.Model):
    """
    Community volunteer — সহায়তা / উদ্ধার / ত্রাণ কার্যক্রম ট্র্যাকিং।
    Point 3: help affected people (people_helped, notes)
    Point 4: join rescue & relief (kind=RESCUE|RELIEF, operation_key)
    Point 5: update own activities (status, note, people_helped)
    """

    class Kind(models.TextChoices):
        ASSISTANCE = "ASSISTANCE", "সহায়তা"
        RELIEF = "RELIEF", "ত্রাণ"
        RESCUE = "RESCUE", "উদ্ধার"
        OTHER = "OTHER", "অন্যান্য"

    class Status(models.TextChoices):
        PENDING = "PENDING", "বাকি"
        ONGOING = "ONGOING", "চলমান"
        DONE = "DONE", "সম্পন্ন"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="volunteer_activities",
    )
    title = models.CharField(max_length=255)
    place = models.CharField(max_length=255, blank=True)
    detail = models.TextField(blank=True)
    note = models.TextField(blank=True)
    kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.ASSISTANCE
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    people_helped = models.PositiveIntegerField(default=0)
    incident_id = models.IntegerField(null=True, blank=True, db_index=True)
    assignment_id = models.IntegerField(null=True, blank=True, db_index=True)
    operation_key = models.CharField(max_length=64, blank=True, db_index=True)
    due_label = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        verbose_name_plural = "volunteer activities"

    def __str__(self):
        return f"{self.user_id}: {self.title} ({self.status})"

    def to_task_dict(self):
        return {
            "id": f"VA-{self.id}",
            "title": self.title,
            "place": self.place or "—",
            "due": self.due_label
            or ("সম্পন্ন" if self.status == "DONE" else "চলমান" if self.status == "ONGOING" else "শীঘ্রই"),
            "status": self.status,
            "detail": self.detail or "",
            "note": self.note or "",
            "kind": self.kind,
            "peopleHelped": self.people_helped,
            "operationKey": self.operation_key or None,
            "incidentId": self.incident_id,
            "updatedAt": int(self.updated_at.timestamp() * 1000) if self.updated_at else None,
            "createdAt": int(self.created_at.timestamp() * 1000) if self.created_at else None,
        }
