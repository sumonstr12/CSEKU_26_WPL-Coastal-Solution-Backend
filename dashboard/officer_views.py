from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Sum, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from alert_notifications.models import Alert, NotificationLog
from incidents.models import (
    IncidentReport,
    Shelter,
    ResponseAssignment,
    ResponseAction,
    VerificationRecord,
)
from users.models import AdministrativeArea, DisasterManagementOfficerProfile
from users.permissions import isDisasterManagementOfficer

from dashboard.views import (
    SEVERITY_RANK,
    alert_matches_district,
    alert_matches_upazila,
)


OFFICER_PERMS = [IsAuthenticated, isDisasterManagementOfficer]

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
    "ঘূর্ণিঝড়": "cyclone", "জলোচ্ছ্বাস": "surge", "বন্যা": "flood",
    "নদীভাঙন": "erosion", "অতিবৃষ্টি": "rainfall",
    "লবণাক্ততা": "salinity", "পানিবন্দী": "waterlogging",
}
ALERT_TYPE_TO_FE = {
    "cyclone": "cyclone", "storm_surge": "surge", "flood": "flood",
    "erosion": "erosion", "general": "flood", "emergency": "surge",
    "preparedness": "cyclone", "evacuation": "surge",
}
NOTIF_KIND = {
    "alert": "alert", "critical_alert": "alert",
    "report_submission": "report", "report_update": "report",
    "assignment": "mission", "reminder": "system", "broadcast": "system",
}
MAP_DISTRICTS = [
    {"name": "সাতক্ষীরা", "x": 86, "y": 398},
    {"name": "খুলনা", "x": 104, "y": 372},
    {"name": "বাগেরহাট", "x": 128, "y": 386},
    {"name": "পিরোজপুর", "x": 152, "y": 372},
    {"name": "বরগুনা", "x": 148, "y": 402},
    {"name": "পটুয়াখালী", "x": 180, "y": 404},
    {"name": "ভোলা", "x": 210, "y": 394},
    {"name": "বরিশাল", "x": 172, "y": 350},
    {"name": "লক্ষ্মীপুর", "x": 226, "y": 336},
    {"name": "নোয়াখালী", "x": 246, "y": 352},
    {"name": "ফেনী", "x": 262, "y": 324},
    {"name": "চট্টগ্রাম", "x": 358, "y": 318},
    {"name": "ককসবাজার", "x": 378, "y": 432},
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


def ms(dt):
    if not dt:
        return None
    return int(dt.timestamp() * 1000)


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


def scoped_incidents(user):
    region_name, district_names, upazila = officer_scope(user)
    qs = IncidentReport.objects.select_related("category", "reporter")
    if district_names:
        qs = qs.filter(district__in=district_names)
    if upazila:
        qs = qs.filter(upazila__icontains=upazila)
    return qs, region_name, district_names, upazila


def serialize_report(r):
    reporter_name = None
    if not r.is_anonymous:
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
        "place": r.village or r.address or "",
        "severity": fe_severity(r),
        "status": fe_status(r),
        "incident_time": r.incident_time,
        "time": r.incident_time or r.created_at,
        "affected": r.affected_people_estimate,
        "category": {"id": r.category_id} if r.category_id else {},
        "reporter": {"name": reporter_name} if reporter_name else None,
    }


def serialize_alert_card(alert):
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


def matching_alerts(district_names, upazila):
    now = timezone.now()
    valid = list(
        Alert.objects.filter(
            is_active=True,
            is_verified=True,
            valid_from__lte=now,
        ).filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=now)
        ).order_by("-published_at")
    )
    if district_names:
        valid = [
            a for a in valid
            if any(alert_matches_district(a, d) for d in district_names)
            or (upazila and alert_matches_upazila(a, upazila))
        ]
    valid.sort(
        key=lambda a: (SEVERITY_RANK.get(a.severity, 0), a.published_at),
        reverse=True,
    )
    return valid


def district_risk_rows(incidents, district_names, alerts):
    now = timezone.now()
    recent = incidents.filter(created_at__gte=now - timedelta(days=30))
    rows = recent.values("district").annotate(reports=Count("id"))
    high_map = {
        row["district"]: row["c"]
        for row in recent.filter(priority__in=["high", "critical"])
        .values("district")
        .annotate(c=Count("id"))
    }
    alert_districts = set()
    for a in alerts:
        alert_districts.update(a.affected_districts or [])

    out, seen = [], set()
    for row in rows:
        name = row["district"]
        if not name:
            continue
        seen.add(name)
        reports = row["reports"]
        high = high_map.get(name, 0)
        boost = 20 if name in alert_districts else 0
        out.append({
            "district": name,
            "risk": min(100, reports * 4 + high * 8 + boost),
            "reports": reports,
            "trend": "up" if high else "same",
        })
    for d in district_names:
        if d not in seen:
            out.append({
                "district": d,
                "risk": 20 if d in alert_districts else 0,
                "reports": 0,
                "trend": "same",
            })
    out.sort(key=lambda x: x["risk"], reverse=True)
    return out


def reports_by_type_rows(incidents):
    open_statuses = ["submitted", "under_review", "verified", "assigned", "in_progress"]
    counts = defaultdict(int)
    for inc in incidents.filter(status__in=open_statuses).select_related("category"):
        counts[fe_report_type(inc.category)] += 1
    data = []
    for key, meta in CATEGORY_META.items():
        if counts.get(key):
            data.append({"label": meta["label"], "value": counts[key], "color": meta["color"]})
    leftover = sum(v for k, v in counts.items() if k not in CATEGORY_META)
    if leftover:
        data.append({"label": "অন্যান্য", "value": leftover, "color": "#94a3b8"})
    return data


def serialize_operations(incidents):
    assignment_qs = (
        ResponseAssignment.objects
        .select_related("incident", "incident__category", "assigned_to", "assigned_to__user")
        .filter(incident__in=incidents)
        .exclude(status__in=["declined", "cancelled"])
        .order_by("-created_at")
    )
    grouped = {}
    for a in assignment_qs:
        rec = grouped.setdefault(a.incident_id, {
            "id": f"OP-{a.incident_id}",
            "title": a.incident.title_bn or a.incident.title or f"উদ্ধার অভিযান #{a.incident_id}",
            "type": (a.incident.category.name_bn if a.incident.category_id else "উদ্ধার"),
            "district": a.incident.district or "",
            "teams": 0,
            "rescued": 0,
            "lead": "",
            "startedAt": ms(a.assignment_time),
            "status": "DONE",
            "_open": False,
        })
        rec["teams"] += 1
        if not rec["lead"] and getattr(a.assigned_to, "user", None):
            rec["lead"] = a.assigned_to.user.full_name
        if a.status in ("pending", "accepted", "in_progress"):
            rec["_open"] = True
        if rec["startedAt"] is None:
            rec["startedAt"] = ms(a.assignment_time)

    rescue_map = {
        row["assignment__incident_id"]: row["total"] or 0
        for row in (
            ResponseAction.objects
            .filter(
                assignment__incident_id__in=list(grouped.keys()),
                action_type__in=["rescue", "evacuation"],
            )
            .values("assignment__incident_id")
            .annotate(total=Sum("personnel_count"))
        )
    }
    ops = []
    for iid, rec in grouped.items():
        rec["status"] = "IN_PROGRESS" if rec.pop("_open") else "DONE"
        rec["rescued"] = rescue_map.get(iid, 0)
        rec["lead"] = rec["lead"] or "—"
        rec["startedAt"] = rec["startedAt"] or ms(timezone.now())
        ops.append(rec)
    ops.sort(key=lambda o: 0 if o["status"] == "IN_PROGRESS" else 1)
    return ops


def serialize_shelter(s):
    return {
        "id": s.id,
        "name": s.name,
        "district": s.district or "",
        "upazila": s.upazila or "",
        "capacity": s.capacity or 0,
        "occupied": s.occupied or 0,
        "status": s.status or "READY",
        "facilities": s.facilities or [],
        "water": bool(s.water),
        "power": bool(s.power),
        "distance": None,
    }


def scoped_shelters(district_names, upazila):
    qs = Shelter.objects.filter(is_active=True)
    if district_names:
        qs = qs.filter(district__in=district_names)
    if upazila:
        qs = qs.filter(upazila__icontains=upazila)
    return qs


# ============================================================
# BADGES
# ============================================================

class OfficerBadgeView(APIView):
    permission_classes = OFFICER_PERMS

    def get(self, request):
        incidents, _, district_names, upazila = scoped_incidents(request.user)
        alerts = matching_alerts(district_names, upazila)
        pending = incidents.filter(status__in=["submitted", "under_review"]).count()
        running = (
            ResponseAssignment.objects
            .filter(incident__in=incidents, status__in=["pending", "accepted", "in_progress"])
            .values("incident_id")
            .distinct()
            .count()
        )
        unread = NotificationLog.objects.filter(
            recipient=request.user, read_at__isnull=True
        ).count()
        critical = sum(
            1 for a in alerts
            if (a.severity or "").lower() in ("critical", "high")
        )
        return Response({
            "notifications": unread,
            "reports": incidents.count(),
            "verification": pending,
            "operations": running,
            "monitoring": critical,
        })


# ============================================================
# REPORTS
# ============================================================

class OfficerReportsView(APIView):
    permission_classes = OFFICER_PERMS

    def get(self, request):
        incidents, *_ = scoped_incidents(request.user)
        rows = [serialize_report(r) for r in incidents.order_by("-created_at")[:200]]
        return Response(rows)


class OfficerVerifyReportView(APIView):
    permission_classes = OFFICER_PERMS

    def post(self, request, pk):
        action = (request.data.get("action") or "").upper()
        try:
            incident = IncidentReport.objects.get(pk=pk)
        except IncidentReport.DoesNotExist:
            return Response({"detail": "Report not found"}, status=404)

        if action == "VERIFY":
            incident.status = "verified"
            incident.save(update_fields=["status", "updated_at"])
            VerificationRecord.objects.create(
                incident=incident,
                verifier=request.user,
                status="verified",
                priority_assigned=incident.priority,
                severity_assigned=incident.severity,
            )
        elif action == "REJECT":
            incident.status = "rejected"
            incident.save(update_fields=["status", "updated_at"])
            VerificationRecord.objects.create(
                incident=incident,
                verifier=request.user,
                status="rejected",
            )
        else:
            return Response({"detail": "Invalid action"}, status=400)

        return Response({"id": incident.id, "action": action})


# ============================================================
# SHELTERS / MAP
# ============================================================

class OfficerSheltersView(APIView):
    permission_classes = OFFICER_PERMS

    def get(self, request):
        _, _, district_names, upazila = scoped_incidents(request.user)
        qs = scoped_shelters(district_names, upazila).exclude(status="MAINTENANCE")
        return Response([serialize_shelter(s) for s in qs])


class OfficerMapView(APIView):
    permission_classes = OFFICER_PERMS

    def get(self, request):
        incidents, _, district_names, upazila = scoped_incidents(request.user)
        alerts = matching_alerts(district_names, upazila)
        risk = {d["district"]: d["risk"] for d in district_risk_rows(incidents, district_names, alerts)}
        reports = [
            serialize_report(r)
            for r in incidents.exclude(status__in=["resolved", "closed", "rejected"]).order_by("-created_at")[:200]
        ]
        shelters = [
            serialize_shelter(s)
            for s in scoped_shelters(district_names, upazila).exclude(status="CLOSED")
        ]
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
# NOTIFICATIONS
# ============================================================

class OfficerNotificationsView(APIView):
    permission_classes = OFFICER_PERMS

    def get(self, request):
        rows = NotificationLog.objects.filter(recipient=request.user).order_by("-created_at")[:80]
        data = []
        for n in rows:
            data.append({
                "id": n.id,
                "kind": NOTIF_KIND.get(n.notification_type, "system"),
                "title": n.subject,
                "body": n.body_bn or n.body or "",
                "time": ms(n.created_at),
                "read": n.read_at is not None,
            })
        return Response(data)


class OfficerNotificationReadAllView(APIView):
    permission_classes = OFFICER_PERMS

    def post(self, request):
        now = timezone.now()
        NotificationLog.objects.filter(
            recipient=request.user, read_at__isnull=True
        ).update(read_at=now, status="read")
        rows = NotificationLog.objects.filter(recipient=request.user).order_by("-created_at")[:80]
        return Response([
            {
                "id": n.id,
                "kind": NOTIF_KIND.get(n.notification_type, "system"),
                "title": n.subject,
                "body": n.body_bn or n.body or "",
                "time": ms(n.created_at),
                "read": True,
            }
            for n in rows
        ])


# ============================================================
# PROFILE STATS
# ============================================================

class OfficerProfileView(APIView):
    permission_classes = OFFICER_PERMS

    def get(self, request):
        incidents, region_name, district_names, upazila = scoped_incidents(request.user)
        verified = incidents.filter(status="verified").count()
        ops = serialize_operations(incidents)
        days_active = max(1, (timezone.now().date() - request.user.date_joined.date()).days)

        activities = []
        for r in incidents.order_by("-created_at")[:6]:
            activities.append({
                "id": str(r.id),
                "kind": "report",
                "title": r.title_bn or r.title or f"রিপোর্ট #{r.id}",
                "place": ", ".join([p for p in [r.upazila, r.district] if p]),
                "time": r.created_at,
            })

        return Response({
            "stats": [
                {"label": "যাচাইকৃত রিপোর্ট", "value": verified, "tone": "lagoon", "icon": "BadgeCheck"},
                {"label": "সমন্বিত অভিযান", "value": len(ops), "tone": "sky", "icon": "LifeBuoy"},
                {"label": "সক্রিয় দিন", "value": days_active, "tone": "emerald", "icon": "CalendarDays"},
            ],
            "activities": activities,
        })


# ============================================================
# SECTION PAGES (monitoring / verification / ops / risk / areas)
# ============================================================

class OfficerSectionView(APIView):
    permission_classes = OFFICER_PERMS

    def get(self, request, key):
        builders = {
            "monitoring": self.monitoring,
            "verification": self.verification,
            "rescue-operations": self.operations,
            "risk-analysis": self.risk_analysis,
            "areas": self.areas,
        }
        fn = builders.get(key)
        if not fn:
            return Response({"stats": [], "blocks": []})
        return Response(fn(request.user))

    def monitoring(self, user):
        incidents, _, district_names, upazila = scoped_incidents(user)
        alerts = matching_alerts(district_names, upazila)
        risk = district_risk_rows(incidents, district_names, alerts)
        ops = serialize_operations(incidents)
        running = sum(1 for o in ops if o["status"] == "IN_PROGRESS")
        return {
            "stats": [
                {"label": "সক্রিয় সতর্কতা", "value": len(alerts), "tone": "red", "icon": "Radar"},
                {"label": "পর্যবেক্ষণাধীন এলাকা", "value": len(risk), "tone": "amber", "icon": "MapPinned"},
                {"label": "চলমান অভিযান", "value": running, "tone": "sky", "icon": "LifeBuoy"},
            ],
            "blocks": [
                {"type": "disasterCards", "title": "সক্রিয় দুর্যোগ পরিস্থিতি", "items": [serialize_alert_card(a) for a in alerts]},
                {"type": "riskBars", "title": "জেলাভিত্তিক ঝুঁকি সূচক", "items": risk},
            ],
        }

    def verification(self, user):
        incidents, *_ = scoped_incidents(user)
        pending_qs = incidents.filter(status__in=["submitted", "under_review"]).order_by("-created_at")
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_verified = incidents.filter(status="verified", updated_at__gte=today).count()
        return {
            "stats": [
                {"label": "যাচাই অপেক্ষিত", "value": pending_qs.count(), "tone": "amber", "icon": "BadgeCheck"},
                {"label": "আজ যাচাইকৃত", "value": today_verified, "tone": "emerald", "icon": "CircleCheck"},
                {"label": "গড় সাড়াদান", "valueText": "—", "tone": "lagoon", "icon": "Timer"},
            ],
            "blocks": [
                {
                    "type": "verificationTable",
                    "title": "যাচাই সারি",
                    "items": [serialize_report(r) for r in pending_qs[:50]],
                }
            ],
        }

    def operations(self, user):
        incidents, *_ = scoped_incidents(user)
        ops = serialize_operations(incidents)
        running = [o for o in ops if o["status"] == "IN_PROGRESS"]
        rescued_72 = sum(o["rescued"] for o in ops)
        teams = sum(o["teams"] for o in running)
        return {
            "stats": [
                {"label": "চলমান অভিযান", "value": len(running), "tone": "red", "icon": "LifeBuoy"},
                {"label": "মোতায়েন দল", "value": teams, "tone": "sky", "icon": "Users"},
                {"label": "উদ্ধারকৃত (৭২ ঘণ্টা)", "value": rescued_72, "tone": "emerald", "icon": "HandHeart"},
            ],
            "blocks": [
                {"type": "operationCards", "title": "উদ্ধার অভিযানসমূহ", "items": ops},
            ],
        }

    def risk_analysis(self, user):
        incidents, _, district_names, upazila = scoped_incidents(user)
        alerts = matching_alerts(district_names, upazila)
        risk = district_risk_rows(incidents, district_names, alerts)
        high = sum(1 for d in risk if d["risk"] >= 60)
        trending = sum(1 for d in risk if d["trend"] == "up")
        return {
            "stats": [
                {"label": "উচ্চ ঝুঁকি জেলা", "value": high, "tone": "red", "icon": "MapPinned"},
                {"label": "বর্ধমান প্রবণতা", "value": trending, "tone": "amber", "icon": "TrendingUp"},
                {"label": "মোট পর্যবেক্ষণ পয়েন্ট", "value": len(risk), "tone": "lagoon", "icon": "Radar"},
            ],
            "blocks": [
                {"type": "riskBars", "title": "জেলাভিত্তিক ঝুঁকি সূচক (শতাংশ)", "items": risk},
                {"type": "typeDonut", "title": "ধরনভিত্তিক ঘটনা বন্টন", "items": reports_by_type_rows(incidents)},
            ],
        }

    def areas(self, user):
        divisions = AdministrativeArea.objects.filter(area_type="DIVISION").prefetch_related("children")
        tree = {}
        district_count = 0
        union_count = AdministrativeArea.objects.filter(area_type="UNION").count()
        for div in divisions:
            districts = {}
            kids = [c for c in div.children.all() if c.area_type == "DISTRICT"]
            district_count += len(kids)
            for dist in kids:
                upazilas = list(
                    dist.children.filter(area_type="UPAZILA").values_list("name", flat=True)
                )
                districts[dist.name] = upazilas
            if districts:
                tree[div.name] = districts
        return {
            "stats": [
                {"label": "বিভাগ", "value": divisions.count(), "tone": "lagoon", "icon": "Landmark"},
                {"label": "উপকূলীয় জেলা", "value": district_count, "tone": "sky", "icon": "MapPinned"},
                {"label": "দুর্যোগপ্রবণ ইউনিয়ন", "value": union_count, "tone": "amber", "icon": "TriangleAlert"},
            ],
            "blocks": [
                {"type": "areaTreeCards", "title": "প্রশাসনিক কাঠামো", "items": tree},
            ],
        }