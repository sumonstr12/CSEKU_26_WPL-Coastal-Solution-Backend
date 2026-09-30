# dashboard/views.py
from math import radians, sin, cos, asin, sqrt

from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import NotFound, PermissionDenied

from alert_notifications.models import Alert, NotificationLog
from incidents.models import IncidentReport, ResponseAction, ResponseAssignment, Shelter
from dashboard.district_coords import get_district_coords
from users.permissions import IsCommunityVolunteer

from .serializers import (
    CitizenOverviewSerializer,
    VolunteerOverviewSerializer,
    VolunteerShelterSerializer,
    VolunteerTaskCompletionSerializer,
    VolunteerTaskSerializer,
)


# ============================================================
# CONFIG
# ============================================================

SEVERITY_RANK = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

NEARBY_RADIUS_KM = 50.0


# ============================================================
# HELPERS
# ============================================================

def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two GPS points in km."""
    if None in (lat1, lon1, lat2, lon2):
        return None

    try:
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
    except (TypeError, ValueError):
        return None

    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def get_user_coords(user):
    """
    Resolve user coordinates.
    Priority:
      1. user.latitude / user.longitude (if present)
      2. district center (static lookup)
    """
    # 1. Direct GPS
    lat = getattr(user, "latitude", None)
    lng = getattr(user, "longitude", None)

    if lat is not None and lng is not None:
        try:
            return float(lat), float(lng)
        except (TypeError, ValueError):
            pass

    # 2. District center
    district = getattr(user, "district", None)
    if district:
        lat, lng = get_district_coords(district)
        if lat is not None:
            return lat, lng

    return None, None


def user_district(user):
    return getattr(user, "district", None)


def user_upazila(user):
    return getattr(user, "upazila", None)


def alert_matches_district(alert, district):
    if not district:
        return False
    return district in (alert.affected_districts or [])


def alert_matches_upazila(alert, upazila):
    if not upazila:
        return False
    return upazila in (alert.affected_upazilas or [])


def select_nearby_shelters(base_qs, user_lat, user_lng, district, upazila, limit=3):
    """
    Fetches nearby shelters with priority chain:
      1. GPS radius (<= NEARBY_RADIUS_KM)
      2. Upazila (icontains)
      3. District (icontains)
      4. Global fallback
    Returns a list of Shelter objects, each with `.distance_km` attribute.
    """
    shelters = list(base_qs)

    # Compute distance for all (if coords available)
    for s in shelters:
        if (
            user_lat is not None
            and user_lng is not None
            and s.latitude is not None
            and s.longitude is not None
        ):
            s.distance_km = haversine_km(
                user_lat, user_lng,
                s.latitude, s.longitude,
            )
            if s.distance_km is not None:
                s.distance_km = round(s.distance_km, 2)
        else:
            s.distance_km = None

    # MODE 1 — GPS radius
    in_radius = [
        s for s in shelters
        if s.distance_km is not None and s.distance_km <= NEARBY_RADIUS_KM
    ]

    if in_radius:
        in_radius.sort(key=lambda s: s.distance_km)
        return in_radius[:limit]

    # MODE 2 — Upazila (case-insensitive)
    if upazila:
        matches = [s for s in shelters if upazila.lower() in (s.upazila or "").lower()]
        if matches:
            matches.sort(key=lambda s: (
                s.distance_km is None,
                s.distance_km if s.distance_km is not None else 9999,
            ))
            return matches[:limit]

    # MODE 3 — District (case-insensitive)
    if district:
        matches = [s for s in shelters if district.lower() in (s.district or "").lower()]
        if matches:
            matches.sort(key=lambda s: (
                s.distance_km is None,
                s.distance_km if s.distance_km is not None else 9999,
            ))
            return matches[:limit]

    # MODE 4 — Global fallback (any 3, sorted by distance)
    shelters.sort(key=lambda s: (
        s.distance_km is None,
        s.distance_km if s.distance_km is not None else 9999,
        s.name or "",
    ))
    return shelters[:limit]


# ============================================================
# CITIZEN DASHBOARD OVERVIEW
# ============================================================

class CitizenOverviewView(APIView):
    """
    GET /api/v1/dashboard/citizen/overview/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        district = user_district(user)
        upazila = user_upazila(user)
        now = timezone.now()

        # ---------------- ALERTS ----------------
        valid_alerts_qs = Alert.objects.filter(
            is_active=True,
            is_verified=True,
            valid_from__lte=now,
        ).filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=now)
        ).order_by("-published_at")

        valid_alerts = list(valid_alerts_qs)

        matching_alerts = [
            a for a in valid_alerts
            if alert_matches_district(a, district)
            or alert_matches_upazila(a, upazila)
        ]

        matching_alerts.sort(
            key=lambda a: (
                SEVERITY_RANK.get(a.severity, 0),
                a.published_at,
            ),
            reverse=True,
        )

        alert = matching_alerts[0] if matching_alerts else None

        # ---------------- BASE SHELTER QUERYSET ----------------
        # No district/upazila filter at DB level — done in Python below.
        base_shelters = (
            Shelter.objects
            .filter(is_active=True)
            .exclude(status="CLOSED")
        )

        # ---------------- USER COORDS ----------------
        user_lat, user_lng = get_user_coords(user)

        # ---------------- NEARBY SHELTERS ----------------
        nearby_shelters = select_nearby_shelters(
            base_qs=base_shelters,
            user_lat=user_lat,
            user_lng=user_lng,
            district=district,
            upazila=upazila,
            limit=3,
        )

        # ---------------- STATS ----------------
        my_reports_qs = IncidentReport.objects.filter(reporter=user)
        my_reports_count = my_reports_qs.count()

        active_disaster_count = len(matching_alerts)

        # Stat card — count of shelters matching user's area (soft match)
        if upazila:
            area_shelters_count = base_shelters.filter(
                upazila__icontains=upazila
            ).count()
        elif district:
            area_shelters_count = base_shelters.filter(
                district__icontains=district
            ).count()
        else:
            area_shelters_count = base_shelters.count()

        warning_count = NotificationLog.objects.filter(
            recipient=user,
            notification_type__in=["alert", "critical_alert"],
            read_at__isnull=True,
        ).count()

        stats = [
            {
                "key": "myReports",
                "label": "আমার রিপোর্ট",
                "value": my_reports_count,
                "tone": "primary",
                "icon": "Megaphone",
            },
            {
                "key": "active",
                "label": "সক্রিয় দুর্যোগ",
                "value": active_disaster_count,
                "tone": "danger",
                "icon": "AlertTriangle",
            },
            {
                "key": "shelters",
                "label": "খোলা আশ্রয়কেন্দ্র",
                "value": area_shelters_count,
                "tone": "info",
                "icon": "Warehouse",
            },
            {
                "key": "warning",
                "label": "সতর্কবার্তা",
                "value": warning_count,
                "tone": "warning",
                "icon": "Bell",
            },
        ]

        # ---------------- MY REPORTS ----------------
        my_reports = (
            my_reports_qs
            .select_related("category")
            .order_by("-created_at")[:5]
        )

        # ---------------- ACTIVITIES ----------------
        activities_qs = IncidentReport.objects.select_related("category")

        if district:
            activities_qs = activities_qs.filter(district=district)

        activities_qs = activities_qs.order_by("-created_at")[:4]

        activities = []
        for r in activities_qs:
            category_name = ""
            if r.category_id:
                category_name = r.category.name_bn or r.category.name or ""

            title = (
                r.title_bn
                or r.title
                or category_name
                or f"রিপোর্ট #{r.id}"
            )

            place_parts = [p for p in [r.upazila, r.district] if p]
            place = ", ".join(place_parts)

            activities.append({
                "id": str(r.id),
                "kind": "report",
                "title": title,
                "place": place,
                "time": r.created_at,
            })

        # ---------------- SERIALIZE ----------------
        payload = {
            "alert": alert,
            "stats": stats,
            "myReports": my_reports,
            "activities": activities,
            "shelters": nearby_shelters,
        }

        serializer = CitizenOverviewSerializer(payload)
        return Response(serializer.data)


class VolunteerOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsCommunityVolunteer]

    def get(self, request, *args, **kwargs):
        now = timezone.now()
        volunteer = getattr(request.user, "volunteer_profile", None)
        assigned_area = volunteer.administrative_area if volunteer else None

        area_nodes = []
        node = assigned_area
        while node:
            area_nodes.append(node)
            node = node.parent

        district = next(
            (area.name for area in area_nodes if area.area_type == "DISTRICT"),
            None,
        )
        upazila = next(
            (area.name for area in area_nodes if area.area_type == "UPAZILA"),
            None,
        )

        area_reports = IncidentReport.objects.none()
        area_shelters = Shelter.objects.none()
        if upazila and district:
            area_reports = IncidentReport.objects.filter(
                district__iexact=district,
                upazila__iexact=upazila,
            )
            area_shelters = Shelter.objects.filter(
                is_active=True,
                district__iexact=district,
                upazila__iexact=upazila,
            ).exclude(status="CLOSED")
        elif district:
            area_reports = IncidentReport.objects.filter(district__iexact=district)
            area_shelters = Shelter.objects.filter(
                is_active=True,
                district__iexact=district,
            ).exclude(status="CLOSED")
        elif upazila:
            area_reports = IncidentReport.objects.filter(upazila__iexact=upazila)
            area_shelters = Shelter.objects.filter(
                is_active=True,
                upazila__iexact=upazila,
            ).exclude(status="CLOSED")

        active_reports = area_reports.exclude(
            status__in=["resolved", "closed", "rejected", "duplicate"]
        )
        pending_reports = area_reports.filter(status__in=["submitted", "under_review"])

        assignments = ResponseAssignment.objects.none()
        active_assignments = ResponseAssignment.objects.none()
        if volunteer:
            assignments = (
                ResponseAssignment.objects
                .filter(assigned_volunteer=volunteer)
                .exclude(status__in=["declined", "cancelled"])
                .select_related("incident", "incident__category")
            )
            active_assignments = assignments.exclude(status="completed")

        alerts = []
        if district or upazila:
            valid_alerts = Alert.objects.filter(
                is_active=True,
                is_verified=True,
                valid_from__lte=now,
            ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=now))
            alerts = [
                alert for alert in valid_alerts
                if alert_matches_district(alert, district)
                or alert_matches_upazila(alert, upazila)
            ]
            alerts.sort(
                key=lambda alert: (
                    SEVERITY_RANK.get(alert.severity, 0),
                    alert.published_at,
                ),
                reverse=True,
            )
        alert = alerts[0] if alerts else None

        incidents_count = active_reports.count()
        shelter_count = area_shelters.count()
        volunteer_count = (
            assigned_area.volunteers.count() if assigned_area else 0
        )
        affected_people = active_reports.aggregate(
            total=Sum("affected_people_estimate")
        )["total"] or 0

        stats = [
            {
                "key": "incidents",
                "label": "স্থানীয় সক্রিয় ঘটনা",
                "value": incidents_count,
                "hint": "আপনার নির্ধারিত এলাকায়",
                "tone": "amber",
                "icon": "Activity",
            },
            {
                "key": "pending",
                "label": "অপেক্ষমাণ রিপোর্ট",
                "value": pending_reports.count(),
                "hint": "যাচাই প্রয়োজন",
                "tone": "lagoon",
                "icon": "ClipboardList",
            },
            {
                "key": "tasks",
                "label": "নির্ধারিত কার্যক্রম",
                "value": active_assignments.count(),
                "hint": "আপনার জন্য বরাদ্দ",
                "tone": "sky",
                "icon": "ListChecks",
            },
            {
                "key": "people",
                "label": "সহায়তাপ্রয়োজন মানুষ",
                "value": affected_people,
                "hint": "সক্রিয় এলাকার রিপোর্ট অনুযায়ী",
                "tone": "emerald",
                "icon": "HandHeart",
            },
        ]

        community_reports = (
            area_reports.select_related("category", "reporter")
            .order_by("-report_time")[:5]
        )

        activities = []
        kind_map = {
            "report_submission": "report",
            "report_update": "report",
            "alert": "alert",
            "critical_alert": "alert",
            "assignment": "mission",
            "reminder": "system",
            "broadcast": "system",
        }
        for notification in NotificationLog.objects.filter(
            recipient=request.user
        ).select_related("incident", "alert").order_by("-created_at")[:8]:
            if notification.incident_id:
                incident = notification.incident
                place = ", ".join(
                    part for part in [incident.upazila, incident.district] if part
                )
            elif notification.alert_id:
                place = ", ".join(
                    (notification.alert.affected_upazilas or [])
                    + (notification.alert.affected_districts or [])
                )
            else:
                place = ", ".join(part for part in [upazila, district] if part)
            activities.append({
                "id": f"notification-{notification.id}",
                "kind": kind_map.get(notification.notification_type, "system"),
                "title": notification.subject,
                "place": place,
                "time": notification.created_at,
            })

        for action in (
            ResponseAction.objects
            .filter(assignment__assigned_volunteer=volunteer)
            .select_related("assignment__incident")
            .order_by("-action_time")[:8]
        ) if volunteer else []:
            incident = action.assignment.incident
            activities.append({
                "id": f"response-action-{action.id}",
                "kind": "mission",
                "title": action.description_bn or action.description,
                "place": ", ".join(
                    part for part in [incident.upazila, incident.district] if part
                ),
                "time": action.action_time,
            })

        for incident in area_reports.select_related("category").order_by("-created_at")[:8]:
            activities.append({
                "id": f"incident-{incident.id}",
                "kind": "report",
                "title": incident.title_bn or incident.title or incident.category.name,
                "place": ", ".join(
                    part for part in [incident.upazila, incident.district] if part
                ),
                "time": incident.created_at,
            })

        activities.sort(key=lambda activity: activity["time"], reverse=True)

        payload = {
            "stats": stats,
            "alert": alert,
            "tasks": assignments,
            "communityReports": community_reports,
            "activities": activities[:8],
            "area": {
                "district": district,
                "upazila": upazila,
                "incidents": incidents_count,
                "shelters": shelter_count,
                "volunteers": volunteer_count,
            },
        }
        serializer = VolunteerOverviewSerializer(payload)
        return Response(serializer.data)


class VolunteerShelterListView(APIView):
    permission_classes = [IsAuthenticated, IsCommunityVolunteer]

    def get(self, request, *args, **kwargs):
        volunteer = getattr(request.user, "volunteer_profile", None)
        assigned_area = volunteer.administrative_area if volunteer else None

        area_nodes = []
        node = assigned_area
        while node:
            area_nodes.append(node)
            node = node.parent

        district = next(
            (area.name for area in area_nodes if area.area_type == "DISTRICT"),
            None,
        )
        upazila = next(
            (area.name for area in area_nodes if area.area_type == "UPAZILA"),
            None,
        )

        incident = None
        incident_id = request.query_params.get("incident")
        if incident_id is not None:
            try:
                incident_id = int(incident_id)
            except (TypeError, ValueError):
                raise NotFound("Incident not found.")

            authorized_incidents = IncidentReport.objects.none()
            if upazila and district:
                authorized_incidents = IncidentReport.objects.filter(
                    district__iexact=district,
                    upazila__iexact=upazila,
                )
            elif district:
                authorized_incidents = IncidentReport.objects.filter(
                    district__iexact=district,
                )
            elif upazila:
                authorized_incidents = IncidentReport.objects.filter(
                    upazila__iexact=upazila,
                )

            incident = get_object_or_404(
                authorized_incidents.select_related("category"),
                pk=incident_id,
            )
            district = incident.district
            upazila = incident.upazila

        shelters = Shelter.objects.none()
        if upazila and district:
            shelters = Shelter.objects.filter(
                is_active=True,
                district__iexact=district,
                upazila__iexact=upazila,
            ).exclude(status="CLOSED")
        elif district:
            shelters = Shelter.objects.filter(
                is_active=True,
                district__iexact=district,
            ).exclude(status="CLOSED")
        elif upazila:
            shelters = Shelter.objects.filter(
                is_active=True,
                upazila__iexact=upazila,
            ).exclude(status="CLOSED")

        serializer = VolunteerShelterSerializer(shelters, many=True)
        payload = {
            "success": True,
            "count": shelters.count(),
            "data": serializer.data,
        }
        if incident is not None:
            payload["incident"] = {
                "id": incident.id,
                "title": incident.title,
                "title_bn": incident.title_bn,
                "category": {
                    "name": incident.category.name,
                    "name_bn": incident.category.name_bn,
                },
                "district": incident.district,
                "upazila": incident.upazila,
            }
        return Response(payload)


class VolunteerTaskStatusUpdateView(APIView):
    """Allows a community volunteer to complete one of their assignments."""

    permission_classes = [IsAuthenticated, IsCommunityVolunteer]

    def patch(self, request, pk, *args, **kwargs):
        input_serializer = VolunteerTaskCompletionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        volunteer = getattr(request.user, "volunteer_profile", None)
        if volunteer is None:
            raise PermissionDenied("A community volunteer profile is required.")
        assignment = get_object_or_404(
            ResponseAssignment.objects.select_related("incident", "incident__category"),
            pk=pk,
            assigned_volunteer=volunteer,
        )

        if assignment.status in {"cancelled", "declined"}:
            return Response(
                {"status": "A cancelled or declined task cannot be completed."},
                status=400,
            )

        # Completing an already completed assignment is deliberately idempotent.
        if assignment.status != "completed":
            assignment.status = "completed"
            assignment.save(update_fields=["status", "updated_at"])

        return Response(VolunteerTaskSerializer(assignment).data)
