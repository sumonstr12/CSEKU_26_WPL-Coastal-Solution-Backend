

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from alert_notifications.models import NotificationLog

from .notification_service import (
    list_notifications,
    mark_all_read,
    mark_one_read,
    serialize_notification,
    unread_count,
)


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in ("0", "false", "no", "off")


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(list_notifications(request.user))


class NotificationSummaryView(APIView):
    """টপবার + সাইডবার ব্যাজ এই সংখ্যা ব্যবহার করে।"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"unread": unread_count(request.user)})


class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        mark_all_read(request.user)
        return Response({
            "unread": 0,
            "items": list_notifications(request.user),
        })


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        read = _as_bool(request.data.get("read", True), default=True)
        try:
            row = mark_one_read(request.user, pk, read)
        except NotificationLog.DoesNotExist:
            return Response({"detail": "Notification not found"}, status=404)
        return Response({
            "item": serialize_notification(row),
            "unread": unread_count(request.user),
        })
