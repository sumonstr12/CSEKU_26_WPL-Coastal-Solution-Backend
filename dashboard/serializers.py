# dashboard/serializers.py
from rest_framework import serializers

from incidents.models import IncidentReport, ResponseAssignment, Shelter
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


class VolunteerShelterSerializer(serializers.ModelSerializer):
    active = serializers.BooleanField(source="is_active", read_only=True)

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
            "active",
            "facilities",
            "water",
            "power",
            "division",
            "union",
            "village",
            "address",
            "latitude",
            "longitude",
        ]


# ============================================================
# FULL OVERVIEW
# ============================================================

class CitizenOverviewSerializer(serializers.Serializer):
    alert = DashboardAlertSerializer(allow_null=True)
    stats = StatCardSerializer(many=True)
    myReports = MyReportRowSerializer(many=True)
    activities = ActivityItemSerializer(many=True)
    shelters = NearbyShelterSerializer(many=True)


class VolunteerAlertSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    severity = serializers.SerializerMethodField()
    areas = serializers.SerializerMethodField()
    startedAt = serializers.DateTimeField(source="published_at")
    signal = serializers.SerializerMethodField()

    class Meta:
        model = Alert
        fields = ["id", "type", "title", "severity", "areas", "startedAt", "signal"]

    def get_type(self, obj):
        return "surge" if obj.alert_type == "storm_surge" else obj.alert_type

    def get_title(self, obj):
        return obj.title_bn or obj.title

    def get_severity(self, obj):
        return obj.severity.upper()

    def get_areas(self, obj):
        return list(dict.fromkeys((obj.affected_upazilas or []) + (obj.affected_districts or [])))

    def get_signal(self, obj):
        return None


class VolunteerCommunityReportSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    severity = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    place = serializers.SerializerMethodField()
    reporter = serializers.SerializerMethodField()
    time = serializers.DateTimeField(source="report_time")
    affected = serializers.IntegerField(source="affected_people_estimate")
    description = serializers.SerializerMethodField()

    class Meta:
        model = IncidentReport
        fields = [
            "id", "type", "severity", "status", "title", "district",
            "upazila", "place", "reporter", "time", "affected", "description",
        ]

    def get_type(self, obj):
        name = (obj.category.name or "").strip().lower().replace(" ", "_")
        aliases = {
            "storm_surge": "surge",
            "tidal_surge": "surge",
            "river_erosion": "erosion",
            "waterlogging": "waterlogging",
        }
        return aliases.get(name, name)

    def get_severity(self, obj):
        return {1: "LOW", 2: "LOW", 3: "MODERATE", 4: "HIGH", 5: "CRITICAL"}.get(obj.severity, "LOW")

    def get_status(self, obj):
        return {
            "submitted": "PENDING",
            "under_review": "PENDING",
            "verified": "VERIFIED",
            "rejected": "REJECTED",
            "duplicate": "DUPLICATE",
            "assigned": "ASSIGNED",
            "in_progress": "IN_PROGRESS",
            "resolved": "RESOLVED",
            "closed": "CLOSED",
        }.get(obj.status, obj.status.upper())

    def get_title(self, obj):
        return obj.title_bn or obj.title or obj.category.name_bn or obj.category.name

    def get_place(self, obj):
        return obj.village or obj.union or obj.address or ""

    def get_reporter(self, obj):
        if obj.is_anonymous:
            name = "Anonymous"
        elif obj.reporter:
            name = obj.reporter.full_name
        else:
            name = obj.reporter_name or ""
        return {"name": name}

    def get_description(self, obj):
        return obj.description_bn or obj.description


class VolunteerTaskSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    place = serializers.SerializerMethodField()
    due = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    detail = serializers.SerializerMethodField()

    class Meta:
        model = ResponseAssignment
        fields = ["id", "title", "place", "due", "status", "detail"]

    def get_title(self, obj):
        incident = obj.incident
        return incident.title_bn or incident.title or incident.category.name_bn or incident.category.name

    def get_place(self, obj):
        incident = obj.incident
        return ", ".join(part for part in [incident.village, incident.upazila, incident.district] if part)

    def get_due(self, obj):
        return obj.response_deadline.isoformat() if obj.response_deadline else ""

    def get_status(self, obj):
        return {
            "pending": "PENDING",
            "accepted": "ONGOING",
            "in_progress": "ONGOING",
            "completed": "DONE",
        }.get(obj.status, "PENDING")

    def get_detail(self, obj):
        return obj.instructions or obj.notes or ""


class VolunteerTaskCompletionSerializer(serializers.Serializer):
    """Validates the single supported action for the volunteer task endpoint."""

    status = serializers.ChoiceField(choices=[("completed", "completed")])


class VolunteerActivitySerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.CharField()
    title = serializers.CharField()
    place = serializers.CharField(allow_blank=True)
    time = serializers.DateTimeField()


class VolunteerAreaSerializer(serializers.Serializer):
    district = serializers.CharField(allow_blank=True, allow_null=True)
    upazila = serializers.CharField(allow_blank=True, allow_null=True)
    incidents = serializers.IntegerField()
    shelters = serializers.IntegerField()
    volunteers = serializers.IntegerField()


class VolunteerStatSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.IntegerField()
    hint = serializers.CharField(required=False, allow_blank=True)
    tone = serializers.CharField()
    icon = serializers.CharField()
    delta = serializers.DictField(required=False)


class VolunteerOverviewSerializer(serializers.Serializer):
    stats = VolunteerStatSerializer(many=True)
    alert = VolunteerAlertSerializer(allow_null=True)
    tasks = VolunteerTaskSerializer(many=True)
    communityReports = VolunteerCommunityReportSerializer(many=True)
    activities = VolunteerActivitySerializer(many=True)
    area = VolunteerAreaSerializer()
