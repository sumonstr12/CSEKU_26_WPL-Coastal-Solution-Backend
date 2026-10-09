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
