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


class ReliefFundingRequest(models.Model):
    """
    Location-based relief funding (NOT per-incident).

    Many citizens may report the same area disaster; officer creates ONE
    manual funding request for that location (district + upazila [+ village]).
    Local Authority APPROVE / REJECT / MODIFY amount.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "অপেক্ষমাণ"
        APPROVED = "APPROVED", "অনুমোদিত"
        REJECTED = "REJECTED", "প্রত্যাখ্যাত"
        MODIFIED = "MODIFIED", "পরিমাণ সংশোধিত"

    requested_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="relief_funding_requests",
    )
    decided_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="relief_funding_decisions",
    )
    # Disaster / event name (manual) — e.g. "কয়রা বন্যা ২০২৬"
    incident_name = models.CharField(max_length=255)
    # Location scope — one active fund per location
    district = models.CharField(max_length=120, db_index=True)
    upazila = models.CharField(max_length=120, blank=True, db_index=True)
    village = models.CharField(max_length=120, blank=True)
    union_name = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    requested_amount = models.DecimalField(max_digits=14, decimal_places=2)
    approved_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    officer_note = models.TextField(blank=True)
    authority_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["district", "upazila", "status"]),
        ]

    def __str__(self):
        return f"Funding#{self.id} {self.incident_name} @ {self.upazila}/{self.district}"

    @property
    def location_label(self):
        parts = [self.village, self.union_name, self.upazila, self.district]
        return ", ".join(p for p in parts if p) or self.district

    def to_dict(self):
        return {
            "id": self.id,
            "incidentName": self.incident_name,
            "title": self.incident_name,  # FE compatibility
            "district": self.district or "",
            "upazila": self.upazila or "",
            "village": self.village or "",
            "union": self.union_name or "",
            "location": self.location_label,
            "description": self.description or "",
            "requestedAmount": float(self.requested_amount),
            "approvedAmount": float(self.approved_amount) if self.approved_amount is not None else None,
            "status": self.status,
            "officerNote": self.officer_note or "",
            "authorityNote": self.authority_note or "",
            "requestedBy": getattr(self.requested_by, "full_name", None) or str(self.requested_by_id),
            "decidedBy": (
                getattr(self.decided_by, "full_name", None) if self.decided_by_id else None
            ),
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "decidedAt": self.decided_at.isoformat() if self.decided_at else None,
        }



class RescueEvent(models.Model):
    """
    Officer-created location-based rescue/relief event.
    Volunteers of that district may join up to max_volunteers.
    """

    class MissionType(models.TextChoices):
        RESCUE = "RESCUE", "উদ্ধার"
        RELIEF = "RELIEF", "ত্রাণ"

    class Status(models.TextChoices):
        OPEN = "OPEN", "খোলা"
        CLOSED = "CLOSED", "বন্ধ"
        DONE = "DONE", "সম্পন্ন"

    title = models.CharField(max_length=255)
    district = models.CharField(max_length=120, db_index=True)
    upazila = models.CharField(max_length=120, blank=True, db_index=True)
    mission_type = models.CharField(
        max_length=20, choices=MissionType.choices, default=MissionType.RESCUE
    )
    max_volunteers = models.PositiveIntegerField(default=10)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_rescue_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"EV-{self.id} {self.title} ({self.district})"

    @property
    def operation_key(self):
        return f"EV-{self.id}"

    def joined_total(self):
        return VolunteerActivity.objects.filter(operation_key=self.operation_key).count()

    def to_dict(self):
        joined = self.joined_total()
        return {
            "id": self.operation_key,
            "eventId": self.id,
            "title": self.title,
            "type": "উদ্ধার" if self.mission_type == "RESCUE" else "ত্রাণ",
            "missionType": self.mission_type,
            "district": self.district or "",
            "upazila": self.upazila or "",
            "teams": joined,
            "maxVolunteers": self.max_volunteers,
            "joinedCount": joined,
            "slotsLeft": max(0, self.max_volunteers - joined),
            "rescued": 0,
            "lead": getattr(self.created_by, "full_name", None) or "—",
            "startedAt": int(self.created_at.timestamp() * 1000) if self.created_at else None,
            "status": "DONE" if self.status in ("DONE", "CLOSED") else "IN_PROGRESS",
            "eventStatus": self.status,
            "note": self.note or "",
            "isLocationEvent": True,
            "canJoin": self.status == "OPEN" and joined < self.max_volunteers,
        }