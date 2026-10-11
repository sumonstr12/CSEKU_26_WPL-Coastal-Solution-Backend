from django.utils import timezone

from alert_notifications.models import NotificationLog

# এক রিকোয়েস্টে সর্বোচ্চ কতগুলো বিজ্ঞপ্তি যাবে
LIST_LIMIT = 80

# ব্যাকএন্ডের notification_type → ফ্রন্টএন্ডের kind
# ফ্রন্টএন্ডের notificationKinds.js-এর কি-এর সাথে মিল রাখুন
NOTIF_KIND = {
    "alert": "alert",
    "critical_alert": "alert",
    "report_submission": "report",
    "report_update": "report",
    "assignment": "mission",
    "reminder": "system",
    "broadcast": "system",
}


def _ms(dt):
    if not dt:
        return None
    return int(dt.timestamp() * 1000)


def serialize_notification(n):
    return {
        "id": n.id,
        "kind": NOTIF_KIND.get(n.notification_type, "system"),
        "type": n.notification_type,
        "title": n.subject,
        "body": n.body_bn or n.body or "",
        "time": _ms(n.created_at),
        "read": n.read_at is not None,
    }


def unread_count(user):
    """সাইডবার ব্যাজ + টপবারের ঘণ্টা — এই সংখ্যাটাই দেখায়।"""
    return NotificationLog.objects.filter(
        recipient=user,
        read_at__isnull=True,
    ).count()


def list_notifications(user, limit=LIST_LIMIT):
    rows = (
        NotificationLog.objects.filter(recipient=user)
        .order_by("-created_at")[:limit]
    )
    return [serialize_notification(n) for n in rows]


def mark_all_read(user):
    now = timezone.now()
    return NotificationLog.objects.filter(
        recipient=user,
        read_at__isnull=True,
    ).update(read_at=now, status="read")


def mark_one_read(user, pk, read=True):
    row = NotificationLog.objects.get(pk=pk, recipient=user)
    if read:
        if row.read_at is None:
            row.read_at = timezone.now()
            row.status = "read"
            row.save(update_fields=["read_at", "status"])
    else:
        row.read_at = None
        if row.status == "read":
            row.status = "delivered"
        row.save(update_fields=["read_at", "status"])
    return row


def notify_user(user, *, subject, body="", body_bn="", notification_type="assignment"):
    """Create one in-app notification for a user. Best-effort on schema differences."""
    if not user:
        return None
    payload = {
        "recipient": user,
        "subject": subject[:255] if subject else "",
        "notification_type": notification_type,
    }
    # Prefer Bengali body when provided
    text = body_bn or body or ""
    field_names = {f.name for f in NotificationLog._meta.get_fields()}
    if "body_bn" in field_names:
        payload["body_bn"] = text
    if "body" in field_names:
        payload["body"] = body or text
    if "status" in field_names:
        payload["status"] = "delivered"
    try:
        return NotificationLog.objects.create(**payload)
    except Exception:
        # Minimal fallback
        try:
            return NotificationLog.objects.create(
                recipient=user,
                subject=subject[:255] if subject else "বিজ্ঞপ্তি",
                notification_type=notification_type,
            )
        except Exception:
            return None


def notify_users(users, **kwargs):
    """Bulk notify; skips None / duplicates."""
    seen = set()
    created = 0
    for u in users:
        if not u or getattr(u, "id", None) in seen:
            continue
        seen.add(u.id)
        if notify_user(u, **kwargs):
            created += 1
    return created