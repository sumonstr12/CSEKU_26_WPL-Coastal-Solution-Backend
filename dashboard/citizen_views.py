"""
Citizen dashboard API — frontend-compatible shapes.

GET  citizen/overview/
GET  citizen/badges/
GET  citizen/shelters/
GET  citizen/map/
GET  citizen/profile/
"""

from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from alert_notifications.models import Alert, NotificationLog
from dashboard.notification_service import unread_count
from dashboard.officer_views import (
    MAP_DISTRICTS,
    district_risk_rows,
    matching_alerts,
    ms,
    serialize_alert_card,
    serialize_report,
    serialize_shelter,
)
from dashboard.views import (
    get_user_coords,
    select_nearby_shelters,
    user_district,
    user_upazila,
)
from incidents.models import IncidentReport, Shelter

PERMS = [IsAuthenticated]

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
    1: "cyclone", 2: "surge", 3: "flood", 4: "erosion",
    5: "rainfall", 6: "salinity", 7: "waterlogging",
}

BN_TYPE_TO_KEY = {
    "ঘূর্ণিঝড়": "cyclone", "জলোচ্ছ্বাস": "surge", "বন্যা": "flood",
    "নদীভাঙন": "erosion", "অতিবৃষ্টি": "rainfall",
    "লবণাক্ততা": "salinity", "পানিবন্দী": "waterlogging",
}

ALERT_TYPE_TO_FE = {
    "cyclone": "cyclone", "storm_surge": "surge", "flood": "flood",
    "erosion": "erosion", "general": "flood", "emergency": "surge",
    "preparedness": "cyclone", "evacuation": "surge",
}


def fe_report_type(category):
    if not category:
        return "flood"
    if category.id in CATEGORY_ID_TO_TYPE:
        return CATEGORY_ID_TO_TYPE[category.id]
    if category.name_bn in BN_TYPE_TO_KEY:
        return BN_TYPE_TO_KEY[category.name_bn]
    name = (category.name or "").lower().replace(" ", "_")
    for key in CATEGORY_ID_TO_TYPE.values():
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


def serialize_citizen_report(r):
    reporter_name = None
    if not getattr(r, "is_anonymous", False):
        reporter_name = r.reporter_name or (
            r.reporter.full_name if r.reporter_id else None
        )
    return {
        "id": r.id,
        "type": fe_report_type(r.category),
        "title": r.title_bn or r.title or (
            r.category.name_bn if r.category_id else f"রিপোর্ট #{r.id}"
        ),
        "description": r.description_bn or r.description or "",
        "district": r.district or "",
        "upazila": r.upazila or "",
        "place": getattr(r, "village", None) or getattr(r, "address", None) or "",
        "severity": fe_severity(r),
        "status": fe_status(r),
        "incident_time": r.incident_time,
        "time": r.incident_time or r.created_at,
        "affected": r.affected_people_estimate,
        "category": {"id": r.category_id} if r.category_id else {},
        "reporter": {"name": reporter_name} if reporter_name else None,
    }


def serialize_citizen_alert(alert):
    if not alert:
        return None
    areas = list(alert.affected_districts or []) or list(alert.affected_upazilas or [])
    return {
        "id": str(alert.id),
        "type": ALERT_TYPE_TO_FE.get(alert.alert_type, "flood"),
        "severity": PRIORITY_TO_FE.get((alert.severity or "").lower(), "MODERATE"),
        "title": alert.title_bn or alert.title,
        "areas": areas,
        "startedAt": ms(alert.published_at),
        "signal": None,
        "affectedEstimate": "—",
        "source": "সতর্কতা কেন্দ্র",
    }


def serialize_citizen_shelter(s, distance_label=None):
    row = {
        "id": s.id,
        "name": s.name,
        "district": s.district or "",
        "upazila": s.upazila or "",
        "capacity": s.capacity or 0,
        "occupied": s.occupied or 0,
        "status": s.status or "READY",
        "facilities": getattr(s, "facilities", None) or [],
        "water": bool(getattr(s, "water", False)),
        "power": bool(getattr(s, "power", False)),
        "distance": distance_label,
    }
    km = getattr(s, "distance_km", None)
    if km is not None and distance_label is None:
        try:
            row["distance"] = f"{float(km):.1f} কিমি"
        except (TypeError, ValueError):
            row["distance"] = None
    return row


def my_reports_qs(user):
    return (
        IncidentReport.objects
        .filter(reporter=user)
        .select_related("category", "reporter")
    )


# ============================================================
# OVERVIEW
# ============================================================

class CitizenOverviewView(APIView):
    """
    GET /dashboard/citizen/overview/
    Shape expected by CitizenDashboard.jsx
    """
    permission_classes = PERMS

    def get(self, request):
        user = request.user
        district = user_district(user)
        upazila = user_upazila(user)
        now = timezone.now()

        # Alerts for user's area
        valid = list(
            Alert.objects.filter(
                is_active=True,
                is_verified=True,
                valid_from__lte=now,
            ).filter(
                Q(valid_until__isnull=True) | Q(valid_until__gte=now)
            ).order_by("-published_at")
        )
        from dashboard.views import alert_matches_district, alert_matches_upazila, SEVERITY_RANK

        matching = [
            a for a in valid
            if alert_matches_district(a, district) or alert_matches_upazila(a, upazila)
        ]
        matching.sort(
            key=lambda a: (SEVERITY_RANK.get(a.severity, 0), a.published_at),
            reverse=True,
        )
        alert = serialize_citizen_alert(matching[0] if matching else None)

        base_shelters = (
            Shelter.objects.filter(is_active=True).exclude(status="CLOSED")
        )
        user_lat, user_lng = get_user_coords(user)
        nearby = select_nearby_shelters(
            base_qs=base_shelters,
            user_lat=user_lat,
            user_lng=user_lng,
            district=district,
            upazila=upazila,
            limit=3,
        )
        shelter_rows = [serialize_citizen_shelter(s) for s in nearby]

        reports_qs = my_reports_qs(user)
        my_count = reports_qs.count()
        active_disaster_count = len(matching)

        if upazila:
            area_shelters_count = base_shelters.filter(upazila__icontains=upazila).count()
        elif district:
            area_shelters_count = base_shelters.filter(district__icontains=district).count()
        else:
            area_shelters_count = base_shelters.count()

        try:
            warning_count = NotificationLog.objects.filter(
                recipient=user,
                notification_type__in=["alert", "critical_alert"],
                read_at__isnull=True,
            ).count()
        except Exception:
            warning_count = unread_count(user)

        stats = [
            {
                "key": "myReports",
                "label": "আমার রিপোর্ট",
                "value": my_count,
                "tone": "lagoon",
                "icon": "Megaphone",
            },
            {
                "key": "active",
                "label": "সক্রিয় দুর্যোগ",
                "value": active_disaster_count,
                "tone": "red",
                "icon": "TriangleAlert",
            },
            {
                "key": "shelters",
                "label": "খোলা আশ্রয়কেন্দ্র",
                "value": area_shelters_count,
                "tone": "sky",
                "icon": "Warehouse",
            },
            {
                "key": "warning",
                "label": "সতর্কবার্তা",
                "value": warning_count,
                "tone": "amber",
                "icon": "Bell",
            },
        ]

        my_reports = [
            serialize_citizen_report(r)
            for r in reports_qs.order_by("-created_at")[:5]
        ]

        # Area activities
        act_qs = IncidentReport.objects.select_related("category")
        if district:
            act_qs = act_qs.filter(district=district)
        activities = []
        for r in act_qs.order_by("-created_at")[:6]:
            title = (
                r.title_bn or r.title
                or (r.category.name_bn if r.category_id else f"রিপোর্ট #{r.id}")
            )
            place_parts = [p for p in [r.upazila, r.district] if p]
            activities.append({
                "id": str(r.id),
                "kind": "report",
                "title": title,
                "place": ", ".join(place_parts),
                "time": r.created_at,
            })

        return Response({
            "alert": alert,
            "stats": stats,
            "myReports": my_reports,
            "activities": activities,
            "shelters": shelter_rows,
        })


# ============================================================
# BADGES
# ============================================================

class CitizenBadgeView(APIView):
    permission_classes = PERMS

    def get(self, request):
        user = request.user
        my_count = my_reports_qs(user).count()
        unread = unread_count(user)
        return Response({
            "notifications": unread,
            "myReports": my_count,
            "reports": my_count,
        })


# ============================================================
# SHELTERS
# ============================================================

class CitizenSheltersView(APIView):
    permission_classes = PERMS

    def get(self, request):
        user = request.user
        district = user_district(user)
        upazila = user_upazila(user)
        user_lat, user_lng = get_user_coords(user)

        qs = Shelter.objects.filter(is_active=True).exclude(status="CLOSED")
        nearby = select_nearby_shelters(
            base_qs=qs,
            user_lat=user_lat,
            user_lng=user_lng,
            district=district,
            upazila=upazila,
            limit=50,
        )
        # If nearby returns few, also include district-filtered list
        if len(nearby) < 5:
            extra = qs
            if district:
                extra = extra.filter(district__icontains=district)
            seen = {s.id for s in nearby}
            for s in extra.order_by("name")[:50]:
                if s.id not in seen:
                    nearby.append(s)
                    seen.add(s.id)

        return Response([serialize_citizen_shelter(s) for s in nearby])


# ============================================================
# MAP
# ============================================================

class CitizenMapView(APIView):
    permission_classes = PERMS

    def get(self, request):
        user = request.user
        district = user_district(user)
        upazila = user_upazila(user)

        incidents = IncidentReport.objects.select_related("category", "reporter")
        if district:
            incidents = incidents.filter(district__icontains=district)

        districts = [district] if district else []
        alerts = matching_alerts(districts, upazila)
        risk = {
            d["district"]: d["risk"]
            for d in district_risk_rows(incidents, districts, alerts)
        }

        reports = [
            serialize_citizen_report(r)
            for r in incidents.exclude(
                status__in=["resolved", "closed", "rejected"]
            ).order_by("-created_at")[:100]
        ]

        shelters_qs = Shelter.objects.filter(is_active=True).exclude(status="CLOSED")
        if district:
            shelters_qs = shelters_qs.filter(district__icontains=district)
        shelters = [serialize_citizen_shelter(s) for s in shelters_qs[:100]]

        map_districts = [
            {**d, "risk": risk.get(d["name"], d.get("risk", 0))}
            for d in MAP_DISTRICTS
        ]

        return Response({
            "reports": reports,
            "shelters": shelters,
            "activeDisasters": [serialize_alert_card(a) for a in alerts],
            "mapDistricts": map_districts,
        })


# ============================================================
# PROFILE
# ============================================================

class CitizenProfileView(APIView):
    permission_classes = PERMS

    def get(self, request):
        user = request.user
        qs = my_reports_qs(user)
        total = qs.count()
        verified = qs.filter(
            status__in=["verified", "assigned", "in_progress", "resolved", "closed"]
        ).count()
        resolved = qs.filter(status__in=["resolved", "closed"]).count()

        activities = []
        for r in qs.order_by("-created_at")[:10]:
            title = (
                r.title_bn or r.title
                or (r.category.name_bn if r.category_id else f"রিপোর্ট #{r.id}")
            )
            activities.append({
                "id": str(r.id),
                "kind": "report",
                "title": title,
                "place": ", ".join([p for p in [r.upazila, r.district] if p]),
                "time": r.created_at,
            })

        return Response({
            "stats": [
                {"label": "মোট রিপোর্ট", "value": total, "tone": "lagoon", "icon": "NotebookPen"},
                {"label": "যাচাইকৃত", "value": verified, "tone": "emerald", "icon": "BadgeCheck"},
                {"label": "সমাধান হয়েছে", "value": resolved, "tone": "sky", "icon": "CircleCheck"},
            ],
            "activities": activities,
        })
