"""
Local Authority dashboard API.

Frontend (AuthorityDashboard + section pages) expects these shapes.
Mount under /api/.../dashboard/

GET  authority/overview/
GET  authority/badges/
GET  authority/reports/
POST authority/reports/<pk>/verify/   { "action": "VERIFY"|"REJECT" }
GET  authority/shelters/
GET  authority/map/
GET  authority/profile/
GET  authority/section/<key>/   key = verification | rescue-operations | areas | reports
"""

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from alert_notifications.models import Alert
from dashboard.notification_service import (
    list_notifications,
    mark_all_read,
    unread_count,
)
from dashboard.officer_views import (
    MAP_DISTRICTS,
    district_risk_rows,
    matching_alerts,
    ms,
    serialize_alert_card,
    serialize_operations,
    serialize_report,
    serialize_shelter,
    scoped_shelters,
)
from incidents.models import (
    IncidentReport,
    ResponseAction,
    ResponseAssignment,
    Shelter,
    VerificationRecord,
)
from users.models import AdministrativeArea


from users.models import LocalAuthorityProfile

from users.permissions import IsLocalAuthority


AUTHORITY_PERMS = [IsAuthenticated, IsLocalAuthority]

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

AUTHORITY_SECTIONS = [
    "verification",
    "rescue-operations",
    "areas",
    "reports",
]


def authority_profile(user):
    if LocalAuthorityProfile is None:
        return None
    return (
        LocalAuthorityProfile.objects
        .filter(user=user)
        .select_related("administrative_area", "administrative_area__parent")
        .first()
    )


def authority_scope(user):
    """
    Return (region_label, district_names, upazila_name, area_meta).

    area_meta keys used by AuthorityDashboard:
      district, upazila, unions, villages, population
    """
    profile = authority_profile(user)
    area = getattr(profile, "administrative_area", None) if profile else None

    district_names = []
    upazila = None
    region = "আপনার এলাকা"
    area_meta = {
        "district": "",
        "upazila": "",
        "unions": 0,
        "villages": 0,
        "population": "—",
    }

    if area:
        if area.area_type == "UPAZILA":
            upazila = area.name
            region = area.name
            area_meta["upazila"] = f"{area.name} উপজেলা" if "উপজেলা" not in area.name else area.name
            if area.parent_id:
                district_names = [area.parent.name]
                area_meta["district"] = f"{area.parent.name} জেলা"
            # child unions / villages if available
            unions_qs = area.children.filter(area_type="UNION")
            area_meta["unions"] = unions_qs.count()
            villages = 0
            for u in unions_qs:
                villages += u.children.filter(area_type="VILLAGE").count()
            area_meta["villages"] = villages or getattr(area, "village_count", 0) or 0
            pop = getattr(area, "population", None) or getattr(profile, "population", None)
            if pop:
                area_meta["population"] = _bn_population(pop)
        elif area.area_type == "DISTRICT":
            district_names = [area.name]
            region = f"{area.name} জেলা"
            area_meta["district"] = region
            area_meta["upazila"] = "সব উপজেলা"
            upazilas = area.children.filter(area_type="UPAZILA")
            area_meta["unions"] = AdministrativeArea.objects.filter(
                parent__in=upazilas, area_type="UNION"
            ).count()
            area_meta["villages"] = getattr(area, "village_count", 0) or 0
            pop = getattr(area, "population", None)
            if pop:
                area_meta["population"] = _bn_population(pop)
        elif area.area_type == "DIVISION":
            region = f"{area.name} অঞ্চল"
            district_names = list(
                area.children.filter(area_type="DISTRICT").values_list("name", flat=True)
            )
            area_meta["district"] = region
            area_meta["upazila"] = "সব জেলা"
        else:
            region = area.name
            district_names = [area.name]
            area_meta["district"] = area.name
    else:
        # Fallback to user fields (common on custom User model)
        dist = getattr(user, "district", None) or ""
        upz = getattr(user, "upazila", None) or ""
        if dist:
            district_names = [dist]
            area_meta["district"] = f"{dist} জেলা" if "জেলা" not in dist else dist
            region = area_meta["district"]
        if upz:
            upazila = upz
            area_meta["upazila"] = f"{upz} উপজেলা" if "উপজেলা" not in upz else upz
            region = area_meta["upazila"]
        # Try AdministrativeArea lookup by name
        if upz:
            aa = AdministrativeArea.objects.filter(
                name__icontains=upz, area_type="UPAZILA"
            ).first()
            if aa:
                area_meta["unions"] = aa.children.filter(area_type="UNION").count()
                villages = 0
                for u in aa.children.filter(area_type="UNION"):
                    villages += u.children.filter(area_type="VILLAGE").count()
                area_meta["villages"] = villages
                pop = getattr(aa, "population", None)
                if pop:
                    area_meta["population"] = _bn_population(pop)

    if not area_meta["district"] and district_names:
        area_meta["district"] = f"{district_names[0]} জেলা"
    if not area_meta["upazila"] and upazila:
        area_meta["upazila"] = f"{upazila} উপজেলা"

    return region, district_names, upazila, area_meta


def _bn_population(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    if n >= 100000:
        lakhs = n / 100000
        if lakhs == int(lakhs):
            return f"{_to_bn_num(int(lakhs))} লক্ষ"
        return f"{_to_bn_num(round(lakhs, 2))} লক্ষ"
    return _to_bn_num(n)


def _to_bn_num(n):
    en = str(n)
    table = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
    return en.translate(table)


def scoped_incidents(user):
    region, district_names, upazila, area_meta = authority_scope(user)
    qs = IncidentReport.objects.select_related("category", "reporter")
    if district_names:
        qs = qs.filter(district__in=district_names)
    if upazila:
        qs = qs.filter(upazila__icontains=upazila)
    return qs, region, district_names, upazila, area_meta


def build_activities(user, limit=8):
    """Recent verification + assignment activity for the authority area."""
    incidents, *_ = scoped_incidents(user)
    items = []

    # Recent verifications
    verifs = (
        VerificationRecord.objects
        .filter(incident__in=incidents)
        .select_related("incident", "verifier")
        .order_by("-created_at")[:limit]
    )
    for v in verifs:
        status_label = "যাচাই করেছেন" if v.status == "verified" else "বাতিল করেছেন"
        who = ""
        if v.verifier_id:
            who = getattr(v.verifier, "full_name", None) or str(v.verifier)
        title = v.incident.title_bn or v.incident.title or f"রিপোর্ট #{v.incident_id}"
        items.append({
            "id": f"v-{v.id}",
            "title": f"{who or 'প্রশাসন'} {status_label}: {title}",
            "time": ms(v.created_at),
            "tone": "emerald" if v.status == "verified" else "red",
            "icon": "BadgeCheck",
        })

    # Recent assignments
    assigns = (
        ResponseAssignment.objects
        .filter(incident__in=incidents)
        .select_related("incident")
        .order_by("-created_at")[:limit]
    )
    for a in assigns:
        title = a.incident.title_bn or a.incident.title or f"অভিযান #{a.incident_id}"
        items.append({
            "id": f"a-{a.id}",
            "title": f"উদ্ধার অভিযান বরাদ্দ: {title}",
            "time": ms(a.assignment_time or a.created_at),
            "tone": "sky",
            "icon": "LifeBuoy",
        })

    items.sort(key=lambda x: x.get("time") or 0, reverse=True)
    return items[:limit]


# ============================================================
# OVERVIEW
# ============================================================

class AuthorityOverviewView(APIView):
    """
    GET /dashboard/authority/overview/
    Shape expected by AuthorityDashboard.jsx
    """
    permission_classes = AUTHORITY_PERMS

    def get(self, request):
        user = request.user
        now = timezone.now()
        incidents, region, district_names, upazila, area_meta = scoped_incidents(user)

        alerts = matching_alerts(district_names, upazila)
        alert = serialize_alert_card(alerts[0]) if alerts else None

        pending_statuses = ["submitted", "under_review"]
        open_statuses = ["submitted", "under_review", "verified", "assigned", "in_progress"]

        total_reports = incidents.count()
        pending_count = incidents.filter(status__in=pending_statuses).count()
        active_disaster_count = len(alerts)

        shelters_qs = scoped_shelters(district_names, upazila).exclude(status="CLOSED")
        active_shelters = shelters_qs.exclude(status="READY").count()
        if active_shelters == 0:
            active_shelters = shelters_qs.count()

        ops = serialize_operations(incidents)
        running_ops = sum(1 for o in ops if o["status"] == "IN_PROGRESS")

        verification_queue = [
            serialize_report(r)
            for r in incidents.filter(status__in=pending_statuses).order_by("-created_at")[:6]
        ]

        shelter_rows = [
            serialize_shelter(s)
            for s in shelters_qs.order_by("-occupied")[:4]
        ]

        activities = build_activities(user)

        stats = [
            {
                "key": "total",
                "label": "সর্বমোট স্থানীয় রিপোর্ট",
                "value": total_reports,
                "hint": region,
                "tone": "lagoon",
                "icon": "FileText",
            },
            {
                "key": "pending",
                "label": "যাচাই অপেক্ষিত",
                "value": pending_count,
                "hint": "দ্রুত পদক্ষেপ প্রয়োজন",
                "tone": "amber",
                "icon": "BadgeCheck",
            },
            {
                "key": "active",
                "label": "সক্রিয় দুর্যোগ",
                "value": active_disaster_count,
                "hint": "অঞ্চল জুড়ে",
                "tone": "orange",
                "icon": "TriangleAlert",
            },
            {
                "key": "shelters",
                "label": "সক্রিয় আশ্রয়কেন্দ্র",
                "value": active_shelters,
                "hint": "জনবল ও মজুদ সচল",
                "tone": "sky",
                "icon": "Warehouse",
            },
            {
                "key": "ops",
                "label": "চলমান উদ্ধার অভিযান",
                "value": running_ops,
                "hint": "সমন্বয়াধীন",
                "tone": "emerald",
                "icon": "LifeBuoy",
            },
        ]

        return Response({
            "stats": stats,
            "alert": alert,
            "verificationQueue": verification_queue,
            "shelters": shelter_rows,
            "operations": ops,
            "area": area_meta,
            "activities": activities,
        })


# ============================================================
# BADGES
# ============================================================

class AuthorityBadgeView(APIView):
    permission_classes = AUTHORITY_PERMS

    def get(self, request):
        incidents, _, district_names, upazila, _ = scoped_incidents(request.user)
        alerts = matching_alerts(district_names, upazila)
        pending = incidents.filter(status__in=["submitted", "under_review"]).count()
        running = (
            ResponseAssignment.objects
            .filter(incident__in=incidents, status__in=["pending", "accepted", "in_progress"])
            .values("incident_id")
            .distinct()
            .count()
        )
        unread = unread_count(request.user)
        return Response({
            "notifications": unread,
            "reports": incidents.count(),
            "verification": pending,
            "operations": running,
            "requests": 0,
            "missions": 0,
        })


# ============================================================
# REPORTS / VERIFY
# ============================================================

class AuthorityReportsView(APIView):
    permission_classes = AUTHORITY_PERMS

    def get(self, request):
        incidents, *_ = scoped_incidents(request.user)
        rows = [serialize_report(r) for r in incidents.order_by("-created_at")[:200]]
        return Response(rows)


class AuthorityVerifyReportView(APIView):
    permission_classes = AUTHORITY_PERMS

    def post(self, request, pk):
        action = (request.data.get("action") or "").upper()
        try:
            incident = IncidentReport.objects.get(pk=pk)
        except IncidentReport.DoesNotExist:
            return Response({"detail": "Report not found"}, status=404)

        # Scope check — authority may only verify in their area
        _, district_names, upazila, _ = authority_scope(request.user)
        if district_names and incident.district not in district_names:
            return Response({"detail": "Outside your administrative area"}, status=403)
        if upazila and upazila not in (incident.upazila or ""):
            return Response({"detail": "Outside your administrative area"}, status=403)

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

class AuthoritySheltersView(APIView):
    permission_classes = AUTHORITY_PERMS

    def get(self, request):
        _, _, district_names, upazila, _ = scoped_incidents(request.user)
        qs = scoped_shelters(district_names, upazila).exclude(status="MAINTENANCE")
        return Response([serialize_shelter(s) for s in qs])


class AuthorityMapView(APIView):
    permission_classes = AUTHORITY_PERMS

    def get(self, request):
        incidents, _, district_names, upazila, _ = scoped_incidents(request.user)
        alerts = matching_alerts(district_names, upazila)
        risk = {
            d["district"]: d["risk"]
            for d in district_risk_rows(incidents, district_names, alerts)
        }
        reports = [
            serialize_report(r)
            for r in incidents.exclude(
                status__in=["resolved", "closed", "rejected"]
            ).order_by("-created_at")[:200]
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
# PROFILE
# ============================================================

class AuthorityProfileView(APIView):
    permission_classes = AUTHORITY_PERMS

    def get(self, request):
        user = request.user
        incidents, *_ = scoped_incidents(user)
        verified = incidents.filter(status="verified").count()
        ops = serialize_operations(incidents)
        coordinated = len(ops)
        # Active days approximation: distinct days with verification activity
        active_days = (
            VerificationRecord.objects
            .filter(verifier=user)
            .dates("created_at", "day")
            .count()
        )
        return Response({
            "stats": [
                {"label": "যাচাইকৃত রিপোর্ট", "value": verified, "tone": "lagoon", "icon": "BadgeCheck"},
                {"label": "সমন্বিত অভিযান", "value": coordinated, "tone": "sky", "icon": "LifeBuoy"},
                {"label": "সক্রিয় দিন", "value": active_days or 0, "tone": "emerald", "icon": "CalendarDays"},
            ],
            "activities": build_activities(user, limit=12),
        })


# ============================================================
# SECTIONS
# ============================================================

class AuthoritySectionView(APIView):
    permission_classes = AUTHORITY_PERMS

    def get(self, request, key):
        builders = {
            "verification": self.verification,
            "rescue-operations": self.operations,
            "areas": self.areas,
            "reports": self.reports_section,
        }
        fn = builders.get(key)
        if not fn:
            return Response({"stats": [], "blocks": []})
        return Response(fn(request.user))

    def verification(self, user):
        incidents, *_ = scoped_incidents(user)
        pending_qs = incidents.filter(
            status__in=["submitted", "under_review"]
        ).order_by("-created_at")
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_verified = incidents.filter(
            status="verified", updated_at__gte=today
        ).count()
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
        rescued = sum(o["rescued"] for o in ops)
        teams = sum(o["teams"] for o in running)
        return {
            "stats": [
                {"label": "চলমান অভিযান", "value": len(running), "tone": "red", "icon": "LifeBuoy"},
                {"label": "মোতায়েন দল", "value": teams, "tone": "sky", "icon": "Users"},
                {"label": "উদ্ধারকৃত (৭২ ঘণ্টা)", "value": rescued, "tone": "emerald", "icon": "HandHeart"},
            ],
            "blocks": [
                {"type": "operationCards", "title": "উদ্ধার অভিযানসমূহ", "items": ops},
            ],
        }

    def reports_section(self, user):
        incidents, region, *_ = scoped_incidents(user)
        now = timezone.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = incidents.filter(created_at__gte=today).count()
        pending = incidents.filter(status__in=["submitted", "under_review"]).count()
        high = incidents.filter(priority__in=["high", "critical"]).exclude(
            status__in=["resolved", "closed", "rejected"]
        ).count()
        rows = [serialize_report(r) for r in incidents.order_by("-created_at")[:100]]
        return {
            "stats": [
                {"label": "আজকের রিপোর্ট", "value": today_count, "tone": "lagoon", "icon": "FileText"},
                {"label": "যাচাই অপেক্ষিত", "value": pending, "tone": "amber", "icon": "BadgeCheck"},
                {"label": "উচ্চ অগ্রাধিকার", "value": high, "tone": "red", "icon": "ShieldAlert"},
            ],
            "blocks": [
                {
                    "type": "reportTable",
                    "title": f"এলাকার রিপোর্ট ({region})",
                    "items": rows,
                }
            ],
        }

    def areas(self, user):
        _, district_names, upazila, area_meta = authority_scope(user)
        incidents, region, _, _, _ = scoped_incidents(user)
        alerts = matching_alerts(district_names, upazila)
        risk_rows = district_risk_rows(incidents, district_names, alerts)
        risk = risk_rows[0] if risk_rows else None

        # Build a small tree focused on authority scope
        tree = {}
        if district_names:
            for dname in district_names:
                dist = AdministrativeArea.objects.filter(
                    name=dname, area_type="DISTRICT"
                ).first()
                if dist:
                    upazilas = list(
                        dist.children.filter(area_type="UPAZILA").values_list("name", flat=True)
                    )
                    parent = dist.parent
                    div_name = parent.name if parent else "অন্যান্য"
                    tree.setdefault(div_name, {})[dist.name] = upazilas
                else:
                    tree.setdefault("অন্যান্য", {})[dname] = [upazila] if upazila else []

        if not tree:
            divisions = AdministrativeArea.objects.filter(
                area_type="DIVISION"
            ).prefetch_related("children")
            for div in divisions:
                districts = {}
                for dist in [c for c in div.children.all() if c.area_type == "DISTRICT"]:
                    upazilas = list(
                        dist.children.filter(area_type="UPAZILA").values_list("name", flat=True)
                    )
                    districts[dist.name] = upazilas
                if districts:
                    tree[div.name] = districts

        recent = [
            serialize_report(r)
            for r in incidents.order_by("-created_at")[:5]
        ]

        return {
            "stats": [
                {"label": "ইউনিয়ন", "value": area_meta.get("unions") or 0, "tone": "lagoon", "icon": "MapPin"},
                {"label": "গ্রাম", "value": area_meta.get("villages") or 0, "tone": "sky", "icon": "Home"},
                {
                    "label": "সক্রিয় রিপোর্ট",
                    "value": incidents.exclude(
                        status__in=["resolved", "closed", "rejected"]
                    ).count(),
                    "tone": "amber",
                    "icon": "FileText",
                },
            ],
            "blocks": [
                {
                    "type": "areaPanel",
                    "title": region,
                    "subtitle": "আপনার দায়িত্বপূর্ণ এলাকা",
                    "area": {
                        "unions": area_meta.get("unions") or 0,
                        "villages": area_meta.get("villages") or 0,
                        "population": area_meta.get("population") or "—",
                        "risk": risk,
                    },
                },
                {
                    "type": "reportTable",
                    "title": "এলাকার সাম্প্রতিক রিপোর্ট",
                    "items": recent,
                },
                {
                    "type": "areaTree",
                    "title": "প্রশাসনিক কাঠামো",
                    "items": tree,
                },
            ],
        }
