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

EDITABLE_STATUSES = {"submitted", "pending", "under_review"}


def can_edit_report(r):
    return (r.status or "").lower() in EDITABLE_STATUSES


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
        "canEdit": can_edit_report(r),
        "canDelete": can_edit_report(r),
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




EDITABLE_STATUSES = {"submitted", "pending", "under_review"}


def can_edit_report(r):
    return (r.status or "").lower() in EDITABLE_STATUSES


def _safe_int(val, default=None):
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _safe_float(val, default=None):
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def collect_citizen_evidence(incident, request=None):
    """List evidence from EvidenceAttachment or generic related names."""
    items = []
    seen = set()

    def add(url, kind="file", name=None):
        if not url or url in seen:
            return
        seen.add(url)
        if request and str(url).startswith("/"):
            url = request.build_absolute_uri(url)
        lower = str(url).lower().split("?")[0]
        if kind == "file":
            if any(lower.endswith(x) for x in (".jpg", ".jpeg", ".png", ".gif", ".webp")):
                kind = "image"
            elif any(lower.endswith(x) for x in (".mp4", ".webm", ".mov")):
                kind = "video"
        items.append({
            "url": url,
            "kind": kind,
            "name": name or str(url).rsplit("/", 1)[-1],
        })

    try:
        from incidents.models import EvidenceAttachment
        for ev in EvidenceAttachment.objects.filter(incident=incident).order_by("id"):
            url = getattr(ev, "file_url", None)
            if not url and getattr(ev, "file_path", None):
                url = getattr(ev, "file_path")
            kind = getattr(ev, "file_type", None) or "file"
            if kind == "photo":
                kind = "image"
            add(
                url,
                kind=kind,
                name=getattr(ev, "original_file_name", None) or getattr(ev, "file_name", None),
            )
    except Exception:
        pass

    if items:
        return items

    for rel in ("evidence", "evidences", "media", "files", "attachments"):
        mgr = getattr(incident, rel, None)
        if not mgr or not hasattr(mgr, "all"):
            continue
        try:
            for obj in mgr.all():
                url = getattr(obj, "file_url", None) or getattr(obj, "url", None)
                f = getattr(obj, "file", None) or getattr(obj, "image", None)
                if f and hasattr(f, "url"):
                    url = f.url
                kind = getattr(obj, "file_type", None) or "file"
                if kind == "photo":
                    kind = "image"
                add(
                    url,
                    kind=kind,
                    name=getattr(obj, "original_file_name", None) or getattr(obj, "name", None),
                )
        except Exception:
            continue
    return items


def serialize_citizen_report(r, request=None, detailed=False):
    reporter_name = None
    if not getattr(r, "is_anonymous", False):
        reporter_name = getattr(r, "reporter_name", None) or (
            r.reporter.full_name if r.reporter_id else None
        )
    row = {
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
        "canEdit": can_edit_report(r),
        "canDelete": can_edit_report(r),
    }
    if not detailed:
        return row

    damage_ids = []
    try:
        if hasattr(r, "damage_types"):
            damage_ids = list(r.damage_types.values_list("id", flat=True))
    except Exception:
        damage_ids = []

    incident_time = r.incident_time
    date_str = ""
    time_str = ""
    if incident_time:
        try:
            local = timezone.localtime(incident_time) if timezone.is_aware(incident_time) else incident_time
            date_str = local.strftime("%Y-%m-%d")
            time_str = local.strftime("%H:%M")
        except Exception:
            pass

    row.update({
        "categoryId": r.category_id,
        "description_bn": getattr(r, "description_bn", None) or r.description or "",
        "situation": getattr(r, "situation", None) or "",
        "damageTypeIds": damage_ids,
        "latitude": getattr(r, "latitude", None),
        "longitude": getattr(r, "longitude", None),
        "locationAccuracy": getattr(r, "location_accuracy", None),
        "locationSource": getattr(r, "location_source", None),
        "address": getattr(r, "address", None) or "",
        "village": getattr(r, "village", None) or "",
        "union": getattr(r, "union", None) or "",
        "division": getattr(r, "division", None) or "",
        "reporterName": getattr(r, "reporter_name", None) or "",
        "reporterPhone": getattr(r, "reporter_phone", None) or "",
        "isAnonymous": bool(getattr(r, "is_anonymous", False)),
        "incidentDate": date_str,
        "incidentTimeOnly": time_str,
        "affectedPeople": r.affected_people_estimate,
        "affectedFamilies": getattr(r, "affected_families_estimate", None),
        "injuriesCount": getattr(r, "injuries_count", None),
        "fatalitiesCount": getattr(r, "fatalities_count", None),
        "isSos": bool(getattr(r, "is_sos", False)),
        "additionalInfo": getattr(r, "additional_info", None) or "",
        "evidence": collect_citizen_evidence(r, request=request),
    })
    return row


# ============================================================
# MY REPORTS — list / update / delete
# ============================================================

class CitizenReportsView(APIView):
    """GET list of the logged-in citizen's own reports."""
    permission_classes = PERMS

    def get(self, request):
        rows = [
            serialize_citizen_report(r)
            for r in my_reports_qs(request.user).order_by("-created_at")[:200]
        ]
        return Response(rows)


class CitizenReportDetailView(APIView):
    """
    GET    citizen/reports/<pk>/   — full detail for edit form
    PATCH  citizen/reports/<pk>/   — update (JSON or multipart)
    DELETE citizen/reports/<pk>/   — delete (pending only)
    """
    permission_classes = PERMS

    def _get_own(self, request, pk):
        try:
            return my_reports_qs(request.user).get(pk=pk)
        except IncidentReport.DoesNotExist:
            return None

    def get(self, request, pk):
        r = self._get_own(request, pk)
        if not r:
            return Response({"detail": "রিপোর্ট পাওয়া যায়নি"}, status=404)
        return Response(serialize_citizen_report(r, request=request, detailed=True))

    def patch(self, request, pk):
        return self._update(request, pk)

    def put(self, request, pk):
        return self._update(request, pk)

    def _update(self, request, pk):
        r = self._get_own(request, pk)
        if not r:
            return Response({"detail": "রিপোর্ট পাওয়া যায়নি"}, status=404)
        if not can_edit_report(r):
            return Response(
                {"detail": "যাচাই/প্রক্রিয়াধীন রিপোর্ট আর সম্পাদনা করা যায় না"},
                status=400,
            )

        data = request.data

        if "description" in data and data.get("description") is not None:
            text = str(data.get("description") or "").strip()
            r.description = text
            if hasattr(r, "description_bn"):
                r.description_bn = text
        if "description_bn" in data and data.get("description_bn") is not None:
            r.description_bn = str(data.get("description_bn") or "").strip()

        if "situation" in data and data.get("situation") is not None:
            r.situation = str(data.get("situation") or "").strip()

        if "category" in data and data.get("category") not in (None, ""):
            cid = _safe_int(data.get("category"))
            if cid is not None:
                r.category_id = cid

        for field in ("district", "upazila", "village", "union", "division", "address"):
            if field in data and data.get(field) is not None and hasattr(r, field):
                setattr(r, field, str(data.get(field) or "").strip())

        if "place" in data and data.get("place") is not None and hasattr(r, "village"):
            r.village = str(data.get("place") or "").strip()

        if any(k in data for k in ("village", "place", "upazila", "district")) and hasattr(r, "address"):
            parts = [
                getattr(r, "village", None) or "",
                r.upazila or "",
                r.district or "",
            ]
            r.address = ", ".join([p for p in parts if p])

        for field, key in (
            ("latitude", "latitude"),
            ("longitude", "longitude"),
            ("location_accuracy", "location_accuracy"),
        ):
            if key in data and hasattr(r, field):
                val = _safe_float(data.get(key))
                if val is not None:
                    setattr(r, field, val)

        if "location_source" in data and hasattr(r, "location_source"):
            r.location_source = str(data.get("location_source") or "")[:32]

        if "incident_time" in data and data.get("incident_time"):
            from django.utils.dateparse import parse_datetime
            raw = str(data.get("incident_time"))
            dt = parse_datetime(raw.replace("Z", "+00:00")) if raw else None
            if dt:
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt, timezone.get_current_timezone())
                r.incident_time = dt
        elif data.get("incident_date") and data.get("incident_time_only"):
            from datetime import datetime as dtmod
            try:
                combined = f"{data.get('incident_date')}T{data.get('incident_time_only')}:00"
                dt = dtmod.fromisoformat(combined)
                r.incident_time = timezone.make_aware(dt, timezone.get_current_timezone())
            except Exception:
                pass

        for model_field, keys in (
            ("affected_people_estimate", ("affected_people_estimate", "affected", "affectedPeople")),
            ("affected_families_estimate", ("affected_families_estimate", "affectedFamilies")),
            ("injuries_count", ("injuries_count",)),
            ("fatalities_count", ("fatalities_count",)),
        ):
            if not hasattr(r, model_field):
                continue
            for k in keys:
                if k in data and data.get(k) not in (None, ""):
                    n = _safe_int(data.get(k), 0)
                    if n is not None:
                        setattr(r, model_field, max(0, n))
                    break

        if "is_sos" in data and hasattr(r, "is_sos"):
            val = data.get("is_sos")
            r.is_sos = str(val).lower() in ("1", "true", "yes", "on")

        if "reporter_name" in data and hasattr(r, "reporter_name"):
            r.reporter_name = str(data.get("reporter_name") or "").strip()[:120]
        if "reporter_phone" in data and hasattr(r, "reporter_phone"):
            r.reporter_phone = str(data.get("reporter_phone") or "").strip()[:20]
        if "additional_info" in data and hasattr(r, "additional_info"):
            r.additional_info = str(data.get("additional_info") or "").strip()

        damage_raw = data.get("damage_types")
        if damage_raw is not None and hasattr(r, "damage_types"):
            ids = []
            if isinstance(damage_raw, (list, tuple)):
                ids = [_safe_int(x) for x in damage_raw]
            else:
                try:
                    ids = [_safe_int(x) for x in request.data.getlist("damage_types")]
                except Exception:
                    ids = [_safe_int(damage_raw)]
            ids = [i for i in ids if i is not None]
            try:
                r.damage_types.set(ids)
            except Exception:
                pass

        try:
            cat = r.category
            loc = r.upazila or r.district
            if cat and loc:
                r.title = f"{cat.name} Incident - {loc}"
            elif cat:
                r.title = f"{cat.name} Incident"
            if hasattr(r, "title_bn") and cat:
                r.title_bn = getattr(cat, "name_bn", None) or r.title
        except Exception:
            pass

        try:
            r.save()
        except Exception as exc:
            return Response({"detail": str(exc)}, status=400)

        files = []
        try:
            files = request.FILES.getlist("files")
        except Exception:
            files = []

        if files:
            image_count = sum(
                1 for f in files if (f.content_type or "").lower().startswith("image/")
            )
            video_count = sum(
                1 for f in files if (f.content_type or "").lower().startswith("video/")
            )
            if image_count > 5:
                return Response({"detail": "Maximum 5 images are allowed."}, status=400)
            if video_count > 1:
                return Response({"detail": "Maximum 1 video is allowed."}, status=400)
            self._attach_files(request, r, files)

        return Response(serialize_citizen_report(r, request=request, detailed=True))

    def _attach_files(self, request, incident, files):
        try:
            from incidents.models import EvidenceAttachment
        except ImportError:
            return

        try:
            from incidents.utils import process_uploaded_file, upload_bytes
        except ImportError:
            try:
                from core.storage import upload_bytes
                process_uploaded_file = None
            except ImportError:
                return

        import uuid

        for uploaded_file in files:
            content_type = (uploaded_file.content_type or "").lower()
            if content_type.startswith("image/"):
                file_type = "photo"
            elif content_type.startswith("video/"):
                file_type = "video"
            elif content_type.startswith("audio/"):
                file_type = "audio"
            else:
                file_type = "document"

            try:
                if process_uploaded_file:
                    processed = process_uploaded_file(uploaded_file)
                    file_data = processed["data"]
                    processed_content_type = processed["content_type"]
                    extension = processed["extension"]
                else:
                    file_data = uploaded_file.read()
                    processed_content_type = content_type or "application/octet-stream"
                    extension = "." + (
                        uploaded_file.name.rsplit(".", 1)[-1]
                        if "." in uploaded_file.name
                        else "bin"
                    )

                unique_name = f"{uuid.uuid4().hex}{extension}"
                file_path = f"incidents/{incident.id}/{unique_name}"
                upload_result = upload_bytes(
                    data=file_data,
                    file_path=file_path,
                    content_type=processed_content_type,
                )
                file_url = (
                    upload_result["url"]
                    if isinstance(upload_result, dict)
                    else str(upload_result)
                )

                EvidenceAttachment.objects.create(
                    incident=incident,
                    uploaded_by=request.user if request.user.is_authenticated else None,
                    file_name=unique_name,
                    original_file_name=uploaded_file.name,
                    file_path=file_path,
                    file_url=file_url,
                    original_file_size=getattr(uploaded_file, "size", None) or len(file_data),
                    file_size=len(file_data),
                    file_type=file_type,
                    mime_type=processed_content_type,
                )
            except Exception:
                continue

    def delete(self, request, pk):
        r = self._get_own(request, pk)
        if not r:
            return Response({"detail": "রিপোর্ট পাওয়া যায়নি"}, status=404)
        if not can_edit_report(r):
            return Response(
                {"detail": "যাচাই/প্রক্রিয়াধীন রিপোর্ট মুছে ফেলা যায় না"},
                status=400,
            )
        r.delete()
        return Response({"id": pk, "deleted": True}, status=200)