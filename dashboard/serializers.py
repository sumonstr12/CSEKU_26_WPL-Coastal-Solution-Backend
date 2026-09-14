# dashboard/serializers.py
from rest_framework import serializers

from incidents.models import IncidentReport
from incidents.models import Shelter   # adjust app name if different
from alert_notifications.models import Alert        # adjust app name if different


# ============================================================
# STAT CARD
# ============================================================

class StatCardSerializer(serializers.Serializer):
    """
    Generic 4-card stat output for the dashboard StatGrid.
    Icons are mapped on the frontend using `key`.
    """
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.IntegerField()
    tone = serializers.CharField()
    icon = serializers.CharField()


# ============================================================
# ACTIVE ALERT (dashboard banner)
# ============================================================

class DashboardAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = [
            "id",
            "alert_type",
            "severity",
            "title",
            "title_bn",
            "content",
            "content_bn",
            "affected_districts",
            "affected_upazilas",
            "valid_from",
            "valid_until",
            "recommended_actions",
            "contact_info",
            "published_at",
        ]


# ============================================================
# MY REPORT ROW (ReportTable)
# ============================================================

class MyReportRowSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source="category.name", read_only=True)
    type_bn = serializers.CharField(source="category.name_bn", read_only=True)

    class Meta:
        model = IncidentReport
        fields = [
            "id",
            "type",
            "type_bn",
            "severity",
            "priority",
            "status",
            "title",
            "title_bn",
            "description",
            "district",
            "upazila",
            "village",
            "affected_people_estimate",
            "report_time",
            "created_at",
        ]


# ============================================================
# ACTIVITY ITEM (RecentActivity)
# ============================================================

class ActivityItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.CharField()   # report | shelter | alert | mission | system
    title = serializers.CharField()
    place = serializers.CharField(allow_blank=True)
    time = serializers.DateTimeField()


# ============================================================
# NEARBY SHELTER
# ============================================================

class NearbyShelterSerializer(serializers.ModelSerializer):
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Shelter
        fields = [
            "id",
            "name",
            "district",
            "upazila",
            "capacity",
            "occupied",
            "status",
            "facilities",
            "water",
            "power",
            "latitude",
            "longitude",
            "distance_km",
        ]

    def get_distance_km(self, obj):
        # Prefer value annotated in the queryset (see view)
        return getattr(obj, "distance_km", None)


# ============================================================
# FULL OVERVIEW
# ============================================================

class CitizenOverviewSerializer(serializers.Serializer):
    alert = DashboardAlertSerializer(allow_null=True)
    stats = StatCardSerializer(many=True)
    myReports = MyReportRowSerializer(many=True)
    activities = ActivityItemSerializer(many=True)
    shelters = NearbyShelterSerializer(many=True)