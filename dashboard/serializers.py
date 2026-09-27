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



# code for week 5(sumon)
# ============================================================
# OFFICER DASHBOARD
# ============================================================

class OfficerStatCardSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.IntegerField()
    tone = serializers.CharField()
    icon = serializers.CharField()
    hint = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ChartSliceSerializer(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.IntegerField()
    color = serializers.CharField(required=False, allow_blank=True)


class DistrictRiskSerializer(serializers.Serializer):
    district = serializers.CharField()
    risk = serializers.IntegerField()
    reports = serializers.IntegerField(required=False)
    trend = serializers.CharField(required=False, allow_blank=True)


class RegionOverviewSerializer(serializers.Serializer):
    name = serializers.CharField()
    alerts = serializers.IntegerField()
    highRisk = serializers.IntegerField()
    pending = serializers.IntegerField()
    districts = DistrictRiskSerializer(many=True)


class OfficerAlertSerializer(serializers.Serializer):
    title = serializers.CharField()
    type = serializers.CharField()
    severity = serializers.CharField()
    areas = serializers.ListField(child=serializers.CharField())
    startedAt = serializers.IntegerField(allow_null=True)
    signal = serializers.CharField(allow_null=True, required=False)
    source = serializers.CharField(allow_null=True, required=False)


class PriorityReportRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    district = serializers.CharField(allow_blank=True)
    upazila = serializers.CharField(allow_blank=True)
    severity = serializers.CharField()
    status = serializers.CharField()
    incident_time = serializers.DateTimeField(allow_null=True)
    time = serializers.DateTimeField(allow_null=True)
    affected = serializers.IntegerField(allow_null=True)
    category = serializers.DictField(required=False)


class OperationRowSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    district = serializers.CharField(allow_blank=True)
    teams = serializers.IntegerField()
    rescued = serializers.IntegerField()
    status = serializers.CharField()


class OfficerOverviewSerializer(serializers.Serializer):
    alert = OfficerAlertSerializer(allow_null=True)
    stats = OfficerStatCardSerializer(many=True)
    region = RegionOverviewSerializer()
    reportsByType = ChartSliceSerializer(many=True)
    monthlyTrend = ChartSliceSerializer(many=True)
    priorityReports = PriorityReportRowSerializer(many=True)
    operations = OperationRowSerializer(many=True)
