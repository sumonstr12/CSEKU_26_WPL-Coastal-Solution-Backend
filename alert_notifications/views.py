from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import NotificationLog


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = NotificationLog.objects.filter(
            recipient=request.user
        ).order_by("-created_at")

        data = []

        for notification in notifications:
            data.append({
                "id": notification.id,
                "type": notification.notification_type,
                "subject": notification.subject,
                "body": notification.body,
                "body_bn": notification.body_bn,
                "status": notification.status,
                "read": notification.read_at is not None,
                "created_at": notification.created_at,
                "read_at": notification.read_at,
                "incident_id": notification.incident_id,
                "alert_id": notification.alert_id,
            })

        return Response({
            "success": True,
            "count": len(data),
            "data": data,
        })


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            notification = NotificationLog.objects.get(
                id=pk,
                recipient=request.user,
            )
        except NotificationLog.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Notification not found.",
                },
                status=404,
            )

        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.status = "read"
            notification.save(
                update_fields=["read_at", "status"]
            )

        return Response({
            "success": True,
            "message": "Notification marked as read.",
            "data": {
                "id": notification.id,
                "read": True,
                "read_at": notification.read_at,
            },
        })


class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        now = timezone.now()

        updated = NotificationLog.objects.filter(
            recipient=request.user,
            read_at__isnull=True,
        ).update(
            read_at=now,
            status="read",
        )

        return Response({
            "success": True,
            "message": "All notifications marked as read.",
            "updated": updated,
        })