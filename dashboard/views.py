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
from .serializers import *
from collections import defaultdict
from datetime import timedelta
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth

from users.models import DisasterManagementOfficerProfile
from users.permissions import isDisasterManagementOfficer


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

# code for week 5 (sumon)
# ============================================================
# OFFICER DASHBOARD OVERVIEW
# ============================================================

STATUS_TO_FE = {
    "submitted": "PENDING",
    "under_review": "PENDING",
    "verified": "VERIFIED",
    "rejected": "REJECTED",
    "duplicate": "REJECTED",
    "assigned": "IN_PROGRESS",
    "in_progress": "IN_PROGRESS",
    "resolved": "RESOLVED",
    "closed": "RESOLVED",
}

PRIORITY_TO_FE = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MODERATE",
    "low": "LOW",
}

CATEGORY_ID_TO_TYPE = {
    1: "cyclone",
    2: "surge",
    3: "flood",
    4: "erosion",
    5: "rainfall",
    6: "salinity",
    7: "waterlogging",
}

CATEGORY_META = {
    "cyclone": {"label": "ঘূর্ণিঝড়", "color": "#0284c7"},
    "surge": {"label": "জলোচ্ছ্বাস", "color": "#2563eb"},
    "flood": {"label": "বন্যা", "color": "#0e7490"},
    "erosion": {"label": "নদীভাঙন", "color": "#b45309"},
    "rainfall": {"label": "অতিবৃষ্টি", "color": "#4f46e5"},
    "salinity": {"label": "লবণাক্ততা", "color": "#047857"},
    "waterlogging": {"label": "পানিবন্দী", "color": "#7c3aed"},
}

BN_TYPE_TO_KEY = {
    "ঘূর্ণিঝড়": "cyclone",
    "জলোচ্ছ্বাস": "surge",
    "বন্যা": "flood",
    "নদীভাঙন": "erosion",
    "অতিবৃষ্টি": "rainfall",
    "লবণাক্ততা": "salinity",
    "পানিবন্দী": "waterlogging",
}

ALERT_TYPE_TO_FE = {
    "cyclone": "cyclone",
    "storm_surge": "surge",
    "flood": "flood",
    "erosion": "erosion",
    "general": "flood",
    "emergency": "surge",
    "preparedness": "cyclone",
    "evacuation": "surge",
}

BN_MONTHS_SHORT = [
    "জানু", "ফেব্রু", "মার্চ", "এপ্রিল", "মে", "জুন",
    "জুলাই", "আগস্ট", "সেপ্টে", "অক্টো", "নভে", "ডিসে",
]


def fe_report_type(category):
    if not category:
        return "flood"
    if category.id in CATEGORY_ID_TO_TYPE:
        return CATEGORY_ID_TO_TYPE[category.id]
    if category.name_bn in BN_TYPE_TO_KEY:
        return BN_TYPE_TO_KEY[category.name_bn]
    name = (category.name or "").lower().replace(" ", "_")
    for key in CATEGORY_META:
        if key in name:
            return key
    return "flood"


def fe_severity(incident):
    mapped = PRIORITY_TO_FE.get((incident.priority or "").lower())
    if mapped:
        return mapped
    score = incident.severity or 1
    if score >= 4:
        return "CRITICAL"
    if score == 3:
        return "HIGH"
    if score == 2:
        return "MODERATE"
    return "LOW"


def fe_status(incident):
    return STATUS_TO_FE.get((incident.status or "").lower(), "PENDING")


def serialize_officer_alert(alert):
    if not alert:
        return None
    areas = list(alert.affected_districts or []) or list(alert.affected_upazilas or [])
    started = None
    if alert.published_at:
        started = int(alert.published_at.timestamp() * 1000)
    return {
        "title": alert.title_bn or alert.title,
        "type": ALERT_TYPE_TO_FE.get(alert.alert_type, "flood"),
        "severity": PRIORITY_TO_FE.get((alert.severity or "").lower(), "MODERATE"),
        "areas": areas,
        "startedAt": started,
        "signal": None,
        "source": None,
    }


def officer_scope(user):
    profile = (
        DisasterManagementOfficerProfile.objects
        .filter(user=user)
        .select_related("administrative_area", "administrative_area__parent")
        .first()
    )

    area = getattr(profile, "administrative_area", None) if profile else None
    upazila = None
    districts = []
    region_name = "আপনার অঞ্চল"

    if area:
        if area.area_type == "DIVISION":
            region_name = f"{area.name} অঞ্চল"
            districts = list(
                area.children.filter(area_type="DISTRICT").values_list("name", flat=True)
            )
        elif area.area_type == "DISTRICT":
            region_name = f"{area.name} জেলা"
            districts = [area.name]
        elif area.area_type == "UPAZILA":
            region_name = area.name
            upazila = area.name
            if area.parent_id:
                districts = [area.parent.name]
        else:
            region_name = area.name
            districts = [area.name]
    elif getattr(user, "district", None):
        region_name = f"{user.district} জেলা"
        districts = [user.district]

    return region_name, districts, upazila


class OfficerOverviewView(APIView):
    """
    GET /api/v1/dashboard/officer/overview/
    Same keys as DisasterOfficerDashboard.jsx already uses.
    """

    permission_classes = [IsAuthenticated, isDisasterManagementOfficer]

    def get(self, request, *args, **kwargs):
        user = request.user
        now = timezone.now()
        region_name, district_names, upazila = officer_scope(user)

        incidents = IncidentReport.objects.select_related("category")
        if district_names:
            incidents = incidents.filter(district__in=district_names)
        if upazila:
            incidents = incidents.filter(upazila__icontains=upazila)

        valid_alerts = list(
            Alert.objects.filter(
                is_active=True,
                is_verified=True,
                valid_from__lte=now,
            ).filter(
                Q(valid_until__isnull=True) | Q(valid_until__gte=now)
            ).order_by("-published_at")
        )

        if district_names:
            matching_alerts = [
                a for a in valid_alerts
                if any(alert_matches_district(a, d) for d in district_names)
                or (upazila and alert_matches_upazila(a, upazila))
            ]
        else:
            matching_alerts = valid_alerts

        matching_alerts.sort(
            key=lambda a: (SEVERITY_RANK.get(a.severity, 0), a.published_at),
            reverse=True,
        )
        alert = serialize_officer_alert(matching_alerts[0] if matching_alerts else None)

        pending_statuses = ["submitted", "under_review"]
        verified_statuses = ["verified"]
        resolved_statuses = ["resolved", "closed"]
        open_statuses = ["submitted", "under_review", "verified", "assigned", "in_progress"]

        pending_count = incidents.filter(status__in=pending_statuses).count()
        verified_count = incidents.filter(status__in=verified_statuses).count()
        active_disaster_count = len(matching_alerts)

        shelters_qs = Shelter.objects.filter(is_active=True).exclude(status="CLOSED")
        if district_names:
            shelters_qs = shelters_qs.filter(district__in=district_names)
        if upazila:
            shelters_qs = shelters_qs.filter(upazila__icontains=upazila)

        available_shelters = shelters_qs.filter(status__in=["OPEN", "READY"])
        available_count = available_shelters.count()
        capacity_total = available_shelters.aggregate(total=Sum("capacity"))["total"] or 0

        assignment_qs = (
            ResponseAssignment.objects
            .select_related("incident")
            .filter(incident__in=incidents)
            .exclude(status__in=["declined", "cancelled"])
        )

        grouped = {}
        for a in assignment_qs:
            rec = grouped.setdefault(a.incident_id, {
                "id": f"OP-{a.incident_id}",
                "title": (
                    a.incident.title_bn
                    or a.incident.title
                    or f"উদ্ধার অভিযান #{a.incident_id}"
                ),
                "district": a.incident.district or "",
                "teams": 0,
                "rescued": 0,
                "status": "DONE",
                "_open": False,
            })
            rec["teams"] += 1
            if a.status in ("pending", "accepted", "in_progress"):
                rec["_open"] = True

        rescue_sums = (
            ResponseAction.objects
            .filter(
                assignment__incident_id__in=list(grouped.keys()),
                action_type__in=["rescue", "evacuation"],
            )
            .values("assignment__incident_id")
            .annotate(total=Sum("personnel_count"))
        )
        rescue_map = {
            row["assignment__incident_id"]: row["total"] or 0
            for row in rescue_sums
        }

        operations = []
        for iid, rec in grouped.items():
            rec["status"] = "IN_PROGRESS" if rec.pop("_open") else "DONE"
            rec["rescued"] = rescue_map.get(iid, 0)
            operations.append(rec)

        operations.sort(key=lambda o: 0 if o["status"] == "IN_PROGRESS" else 1)
        operations = operations[:6]
        running_ops = sum(1 for o in operations if o["status"] == "IN_PROGRESS")
        ops_districts = len({o["district"] for o in operations if o["district"]})

        since_30 = now - timedelta(days=30)
        recent = incidents.filter(created_at__gte=since_30)
        district_rows = (
            recent.values("district")
            .annotate(reports=Count("id"))
            .order_by("-reports")
        )

        high_priority_by_district = {
            row["district"]: row["c"]
            for row in (
                recent.filter(priority__in=["high", "critical"])
                .values("district")
                .annotate(c=Count("id"))
            )
        }

        alert_districts = set()
        for a in matching_alerts:
            alert_districts.update(a.affected_districts or [])

        district_risk = []
        seen = set()
        for row in district_rows:
            name = row["district"]
            if not name:
                continue
            seen.add(name)
            reports = row["reports"]
            high = high_priority_by_district.get(name, 0)
            boost = 20 if name in alert_districts else 0
            district_risk.append({
                "district": name,
                "risk": min(100, reports * 4 + high * 8 + boost),
                "reports": reports,
                "trend": "up" if high else "same",
            })

        for d in district_names:
            if d not in seen:
                district_risk.append({
                    "district": d,
                    "risk": 20 if d in alert_districts else 0,
                    "reports": 0,
                    "trend": "same",
                })

        district_risk.sort(key=lambda x: x["risk"], reverse=True)
        high_risk_count = sum(1 for d in district_risk if d["risk"] >= 60)

        type_counts = defaultdict(int)
        for inc in incidents.filter(status__in=open_statuses).select_related("category"):
            type_counts[fe_report_type(inc.category)] += 1

        reports_by_type = []
        for key, meta in CATEGORY_META.items():
            value = type_counts.get(key, 0)
            if value:
                reports_by_type.append({
                    "label": meta["label"],
                    "value": value,
                    "color": meta["color"],
                })
        leftover = sum(v for k, v in type_counts.items() if k not in CATEGORY_META)
        if leftover:
            reports_by_type.append({
                "label": "অন্যান্য",
                "value": leftover,
                "color": "#94a3b8",
            })

        month_rows = (
            incidents.filter(
                status__in=["verified", "assigned", "in_progress", "resolved", "closed"],
                created_at__gte=now - timedelta(days=210),
            )
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(value=Count("id"))
        )
        month_map = {}
        for row in month_rows:
            m = row["month"]
            if m:
                month_map[(m.year, m.month)] = row["value"]

        y, mo = now.year, now.month
        month_pairs = []
        for _ in range(7):
            month_pairs.append((y, mo))
            mo -= 1
            if mo == 0:
                mo = 12
                y -= 1
        month_pairs.reverse()

        monthly_trend = [
            {"label": BN_MONTHS_SHORT[m - 1], "value": month_map.get((yy, m), 0)}
            for yy, m in month_pairs
        ]

        priority_qs = (
            incidents.filter(priority__in=["high", "critical"])
            .exclude(status__in=resolved_statuses + ["rejected", "duplicate"])
            .order_by("-created_at")[:5]
        )
        priority_reports = []
        for r in priority_qs:
            t = fe_report_type(r.category)
            priority_reports.append({
                "id": r.id,
                "type": t,
                "title": r.title_bn or r.title or (
                    r.category.name_bn if r.category_id else f"রিপোর্ট #{r.id}"
                ),
                "description": r.description_bn or r.description or "",
                "district": r.district or "",
                "upazila": r.upazila or "",
                "severity": fe_severity(r),
                "status": fe_status(r),
                "incident_time": r.incident_time,
                "time": r.incident_time or r.created_at,
                "affected": r.affected_people_estimate,
                "category": {"id": r.category_id} if r.category_id else {},
            })

        stats = [
            {
                "key": "active",
                "label": "সক্রিয় দুর্যোগ",
                "value": active_disaster_count,
                "hint": region_name,
                "tone": "red",
                "icon": "Radar",
            },
            {
                "key": "riskAreas",
                "label": "উচ্চ ঝুঁকিপূর্ণ এলাকা",
                "value": high_risk_count,
                "hint": "পূর্বাভাস বিশ্লেষণে",
                "tone": "amber",
                "icon": "MapPinned",
            },
            {
                "key": "pending",
                "label": "অপেক্ষমাণ রিপোর্ট",
                "value": pending_reports.count(),
                "hint": "যাচাই প্রয়োজন",
                "value": pending_count,
                "hint": "যাচাই সারিতে",
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
                "key": "ops",
                "label": "চলমান উদ্ধার অভিযান",
                "value": running_ops,
                "hint": f"{ops_districts}টি জেলায়" if ops_districts else "সমন্বয়াধীন",
                "tone": "sky",
                "icon": "LifeBuoy",
            },
            {
                "key": "shelters",
                "label": "উপলব্ধ আশ্রয়কেন্দ্র",
                "value": available_count,
                "hint": f"মোট ধারণক্ষমতা {capacity_total:,}",
                "tone": "emerald",
                "icon": "Warehouse",
            },
            {
                "key": "verified",
                "label": "যাচাইকৃত ঘটনা",
                "value": verified_count,
                "hint": "চলতি মৌসুমে",
                "tone": "sand",
                "icon": "BadgeCheck",
            },
        ]

        payload = {
            "alert": alert,
            "stats": stats,
            "region": {
                "name": region_name,
                "alerts": active_disaster_count,
                "highRisk": high_risk_count,
                "pending": pending_count,
                "districts": district_risk[:5],
            },
            "reportsByType": reports_by_type,
            "monthlyTrend": monthly_trend,
            "priorityReports": priority_reports,
            "operations": operations,
        }

        serializer = OfficerOverviewSerializer(payload)
        return Response(serializer.data)
