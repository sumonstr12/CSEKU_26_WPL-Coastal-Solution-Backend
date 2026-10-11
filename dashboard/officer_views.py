from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Sum, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from alert_notifications.models import Alert
from incidents.models import (
    IncidentReport,
    Shelter,
    ResponseAssignment,
    ResponseAction,
    VerificationRecord,
)
from users.models import AdministrativeArea, DisasterManagementOfficerProfile
from dashboard.notification_service import (
    list_notifications,
    mark_all_read,
    unread_count,
    notify_users,
)
from dashboard.models import ReliefFundingRequest, RescueEvent
from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission

User = get_user_model()

try:
    from users.permissions import isDisasterManagementOfficer
except ImportError:
    isDisasterManagementOfficer = None

from dashboard.views import (
    SEVERITY_RANK,
    alert_matches_district,
    alert_matches_upazila,
)


class IsDisasterOfficer(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if isDisasterManagementOfficer is not None:
            try:
                if bool(isDisasterManagementOfficer(user)):
                    return True
            except Exception:
                pass
        role = (getattr(user, "role", None) or "").upper()
        return role in (
            "DISASTER_MANAGEMENT_OFFICER",
            "DISASTER_OFFICER",
            "OFFICER",
        )


OFFICER_PERMS = [IsAuthenticated, IsDisasterOfficer]

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
    reporter_phone = None
    if not getattr(r, "is_anonymous", False):
        reporter_name = getattr(r, "reporter_name", None) or (
            r.reporter.full_name if r.reporter_id else None
        )
        if r.reporter_id:
            u = r.reporter
            reporter_phone = (
                getattr(u, "phone_number", None)
                or getattr(u, "phone", None)
                or getattr(u, "mobile", None)
            )
        if not reporter_phone:
            reporter_phone = getattr(r, "reporter_phone", None) or getattr(r, "contact_phone", None)
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
        "rawStatus": (r.status or "").lower(),
        "incident_time": r.incident_time,
        "time": r.incident_time or r.created_at,
        "affected": r.affected_people_estimate,
        "category": {"id": r.category_id} if r.category_id else {},
        "reporter": {"name": reporter_name, "phone": reporter_phone} if (reporter_name or reporter_phone) else None,
        "reporterPhone": reporter_phone,
        "isAnonymous": bool(getattr(r, "is_anonymous", False)),
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
        unread = unread_count(request.user)
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
    """
    Change report verification status anytime (editable, not one-shot).

    POST body:
      { "action": "VERIFY"|"REJECT"|"PENDING"|"UNDER_REVIEW"|"RESOLVED" }
      or { "status": "verified"|"rejected"|"submitted"|"under_review"|"resolved" }
    """
    permission_classes = OFFICER_PERMS

    ACTION_TO_STATUS = {
        "VERIFY": "verified",
        "VERIFIED": "verified",
        "REJECT": "rejected",
        "REJECTED": "rejected",
        "PENDING": "submitted",
        "SUBMITTED": "submitted",
        "UNDER_REVIEW": "under_review",
        "RESOLVED": "resolved",
        "CLOSED": "closed",
        "ASSIGNED": "assigned",
        "IN_PROGRESS": "in_progress",
    }

    def post(self, request, pk):
        action = (request.data.get("action") or "").upper()
        status_raw = (request.data.get("status") or "").lower().strip()

        try:
            incident = IncidentReport.objects.select_related("reporter", "category").get(pk=pk)
        except IncidentReport.DoesNotExist:
            return Response({"detail": "Report not found"}, status=404)

        if status_raw:
            new_status = status_raw
        elif action in self.ACTION_TO_STATUS:
            new_status = self.ACTION_TO_STATUS[action]
        else:
            return Response(
                {
                    "detail": "Invalid action/status. Use VERIFY, REJECT, PENDING, UNDER_REVIEW, RESOLVED "
                    "or status=verified|rejected|submitted|under_review|resolved"
                },
                status=400,
            )

        allowed = {
            "submitted", "under_review", "verified", "rejected",
            "assigned", "in_progress", "resolved", "closed", "duplicate",
        }
        if new_status not in allowed:
            return Response({"detail": f"Unsupported status: {new_status}"}, status=400)

        old = incident.status
        incident.status = new_status
        try:
            incident.save(update_fields=["status", "updated_at"])
        except Exception:
            incident.save(update_fields=["status"])

        # Log verification record for verify/reject transitions
        vr_status = None
        if new_status == "verified":
            vr_status = "verified"
        elif new_status == "rejected":
            vr_status = "rejected"
        if vr_status:
            try:
                VerificationRecord.objects.create(
                    incident=incident,
                    verifier=request.user,
                    status=vr_status,
                    priority_assigned=getattr(incident, "priority", None),
                    severity_assigned=getattr(incident, "severity", None),
                )
            except Exception:
                try:
                    VerificationRecord.objects.create(
                        incident=incident,
                        verifier=request.user,
                        status=vr_status,
                    )
                except Exception:
                    pass

        return Response({
            "id": incident.id,
            "action": action or new_status.upper(),
            "status": fe_status(incident),
            "rawStatus": new_status,
            "previousStatus": old,
            "message": f"স্ট্যাটাস আপডেট: {old} → {new_status}",
        })


def _officer_collect_evidence(incident, request=None):
    items = []
    seen = set()

    def add(url, kind="file", name=None):
        if not url or url in seen:
            return
        seen.add(url)
        if request and str(url).startswith("/"):
            url = request.build_absolute_uri(url)
        lower = str(url).lower().split("?")[0]
        if kind in ("file", "document", "photo"):
            if kind == "photo" or any(lower.endswith(x) for x in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
                kind = "image"
            elif any(lower.endswith(x) for x in (".mp4", ".webm", ".mov", ".avi", ".mkv")):
                kind = "video"
        items.append({"url": url, "kind": kind, "name": name or str(url).rsplit("/", 1)[-1]})

    try:
        from incidents.models import EvidenceAttachment
        for ev in EvidenceAttachment.objects.filter(incident=incident).order_by("id"):
            url = getattr(ev, "file_url", None) or getattr(ev, "file_path", None)
            kind = getattr(ev, "file_type", None) or "file"
            name = getattr(ev, "original_file_name", None) or getattr(ev, "file_name", None)
            add(url, kind=kind, name=name)
    except Exception:
        pass
    return items


class OfficerReportDetailView(APIView):
    """GET officer/reports/<pk>/ — full detail + evidence + reporter contact."""
    permission_classes = OFFICER_PERMS

    def get(self, request, pk):
        incidents, *_ = scoped_incidents(request.user)
        incident = incidents.select_related("category", "reporter").filter(pk=pk).first()
        if not incident:
            incident = IncidentReport.objects.select_related("category", "reporter").filter(pk=pk).first()
        if not incident:
            return Response({"detail": f"রিপোর্ট #{pk} পাওয়া যায়নি"}, status=404)

        base = serialize_report(incident)
        lat = getattr(incident, "latitude", None) or getattr(incident, "lat", None)
        lng = getattr(incident, "longitude", None) or getattr(incident, "lng", None)
        base.update({
            "address": getattr(incident, "address", None) or "",
            "village": getattr(incident, "village", None) or "",
            "union": getattr(incident, "union", None) or "",
            "isSos": bool(getattr(incident, "is_sos", False)),
            "situation": getattr(incident, "situation", None) or "",
            "latitude": lat,
            "longitude": lng,
            "createdAt": getattr(incident, "created_at", None),
            "updatedAt": getattr(incident, "updated_at", None),
            "evidence": _officer_collect_evidence(incident, request=request),
            "statusOptions": [
                {"value": "PENDING", "label": "অপেক্ষমাণ (pending)"},
                {"value": "UNDER_REVIEW", "label": "পর্যালোচনাধীন"},
                {"value": "VERIFIED", "label": "যাচাইকৃত (সত্য)"},
                {"value": "REJECTED", "label": "প্রত্যাখ্যাত (মিথ্যা)"},
                {"value": "RESOLVED", "label": "সমাধানকৃত"},
            ],
        })
        return Response(base)


def _district_volunteers(district, exclude_user=None):
    """Volunteers in same district (User.district only — no upazila on User)."""
    qs = User.objects.filter(role__in=["COMMUNITY_VOLUNTEER", "VOLUNTEER"])
    if exclude_user is not None:
        qs = qs.exclude(pk=exclude_user.pk)
    if district:
        qs = qs.filter(district__icontains=district)
    return list(qs[:80])


class OfficerAnnounceEventView(APIView):
    """
    POST officer/reports/<pk>/announce/
    Body: { mission_type: "RESCUE"|"RELIEF", note? }
    Officer announces rescue or relief mission from VERIFIED incident.
    Volunteers are notified and can join.
    """
    permission_classes = OFFICER_PERMS

    def post(self, request, pk):
        try:
            incident = IncidentReport.objects.select_related("category").get(pk=pk)
        except IncidentReport.DoesNotExist:
            return Response({"detail": "Report not found"}, status=404)

        status = (incident.status or "").lower()
        if status not in ("verified", "assigned", "in_progress"):
            return Response(
                {
                    "detail": "শুধু যাচাইকৃত (verified) রিপোর্ট থেকে ইভেন্ট ঘোষণা করা যায়। "
                    f"বর্তমান অবস্থা: {incident.status}"
                },
                status=400,
            )

        mission_type = (request.data.get("mission_type") or request.data.get("kind") or "RESCUE").upper()
        if mission_type not in ("RESCUE", "RELIEF"):
            mission_type = "RESCUE"

        kind_bn = "উদ্ধার" if mission_type == "RESCUE" else "ত্রাণ"
        op_prefix = "OP" if mission_type == "RESCUE" else "REL"
        op_key = f"{op_prefix}-{incident.id}"

        existing = (
            ResponseAssignment.objects
            .filter(incident=incident)
            .exclude(status__in=["declined", "cancelled", "completed"])
            .first()
        )
        if existing:
            return Response({
                "id": incident.id,
                "operation": {
                    "id": op_key,
                    "title": incident.title_bn or incident.title or f"{kind_bn} অভিযান #{incident.id}",
                    "district": incident.district or "",
                    "upazila": incident.upazila or "",
                    "missionType": mission_type,
                },
                "notified": 0,
                "message": "এই রিপোর্টের জন্য অভিযান ইতিমধ্যে চলমান।",
                "alreadyExists": True,
            })

        asg = None
        try:
            asg = ResponseAssignment.objects.create(incident=incident, status="pending")
        except Exception:
            try:
                asg = ResponseAssignment.objects.create(incident=incident)
            except Exception:
                asg = None

        if status == "verified":
            try:
                incident.status = "assigned"
                incident.save(update_fields=["status", "updated_at"])
            except Exception:
                pass

        place = ", ".join(
            p for p in [getattr(incident, "village", None), incident.upazila, incident.district] if p
        ) or (getattr(incident, "address", None) or "")
        title = incident.title_bn or incident.title or f"{kind_bn} অভিযান #{incident.id}"
        officer_name = getattr(request.user, "full_name", None) or str(request.user)
        note = (request.data.get("note") or "").strip()

        subject = f"নতুন {kind_bn} ইভেন্ট — {place or incident.district or 'এলাকা'}"
        body = (
            f"কর্মকর্তা {officer_name} যাচাইকৃত রিপোর্ট থেকে {kind_bn} মিশন ঘোষণা করেছেন: {title}. "
            f"লোকেশন: {place}. ড্যাশবোর্ড → উদ্ধার ও ত্রাণ থেকে অংশ নিতে পারেন।"
        )
        if note:
            body += f" নোট: {note}"

        peers = _district_volunteers(incident.district, exclude_user=request.user)
        notified = 0
        try:
            notified = notify_users(
                peers, subject=subject, body=body, body_bn=body, notification_type="assignment"
            )
        except Exception:
            notified = 0

        return Response({
            "id": incident.id,
            "action": "ANNOUNCE",
            "status": incident.status,
            "operation": {
                "id": op_key,
                "title": title,
                "district": incident.district or "",
                "upazila": incident.upazila or "",
                "place": place,
                "missionType": mission_type,
                "assignmentId": asg.id if asg else None,
            },
            "notified": notified,
            "message": f"{kind_bn} ইভেন্ট ঘোষণা হয়েছে। {notified} জন স্বেচ্ছাসেবককে জানানো হয়েছে।",
        })


class OfficerFundingListCreateView(APIView):
    """
    Location-based relief funding (manual, not per incident).

    GET  officer/funding/
    POST officer/funding/
      {
        incident_name, district, upazila?, village?, union?,
        amount, description?, note?
      }

    Only ONE active request (PENDING/APPROVED/MODIFIED) per district+upazila.
    """
    permission_classes = OFFICER_PERMS

    def get(self, request):
        rows = [
            r.to_dict()
            for r in ReliefFundingRequest.objects.filter(requested_by=request.user)[:100]
        ]
        return Response(rows)

    def post(self, request):
        data = request.data
        try:
            amount = float(data.get("amount") or data.get("requested_amount") or 0)
        except (TypeError, ValueError):
            return Response({"detail": "amount অবৈধ"}, status=400)
        if amount <= 0:
            return Response({"detail": "amount ০ এর বেশি হতে হবে"}, status=400)

        incident_name = (
            data.get("incident_name")
            or data.get("incidentName")
            or data.get("title")
            or ""
        ).strip()
        district = (data.get("district") or "").strip()
        upazila = (data.get("upazila") or "").strip()
        village = (data.get("village") or "").strip()
        union_name = (data.get("union") or data.get("union_name") or "").strip()
        description = (data.get("description") or "").strip()
        note = (data.get("note") or data.get("officer_note") or "").strip()

        if not incident_name:
            return Response({"detail": "incident_name (দুর্যোগ/ঘটনার নাম) আবশ্যক"}, status=400)
        if not district:
            return Response({"detail": "district (জেলা) আবশ্যক"}, status=400)

        # One active fund per location (district + upazila)
        active = ReliefFundingRequest.objects.filter(
            district__iexact=district,
            upazila__iexact=upazila,
            status__in=[
                ReliefFundingRequest.Status.PENDING,
                ReliefFundingRequest.Status.APPROVED,
                ReliefFundingRequest.Status.MODIFIED,
            ],
        ).first()
        if active:
            return Response(
                {
                    "detail": (
                        f"এই এলাকার ({upazila or '—'}, {district}) জন্য ইতিমধ্যে "
                        f"একটি সক্রিয় তহবিল অনুরোধ আছে (#{active.id}, {active.status})। "
                        "নতুন করে যোগ করা যাবে না।"
                    ),
                    "existing": active.to_dict(),
                },
                status=400,
            )

        row = ReliefFundingRequest.objects.create(
            requested_by=request.user,
            incident_name=incident_name,
            district=district,
            upazila=upazila,
            village=village,
            union_name=union_name,
            description=description,
            requested_amount=amount,
            officer_note=note,
            status=ReliefFundingRequest.Status.PENDING,
        )

        # Notify only Local Authority of THIS district (বাগেরহাট → Bagerhat authority)
        try:
            peers = _district_authorities(district, upazila)
            loc = ", ".join(p for p in [village, upazila, district] if p)
            notify_users(
                peers,
                subject=f"ত্রাণ তহবিল অনুরোধ — {incident_name}",
                body=(
                    f"{getattr(request.user, 'full_name', request.user)} "
                    f"{amount:,.0f} টাকার ত্রাণ তহবিল চেয়েছেন। "
                    f"ঘটনা: {incident_name}. এলাকা: {loc}. "
                    f"ড্যাশবোর্ড → ত্রাণ তহবিল থেকে সিদ্ধান্ত নিন।"
                ),
                body_bn="",
                notification_type="assignment",
            )
        except Exception:
            pass

        return Response(row.to_dict(), status=201)


class OfficerFundingDetailView(APIView):
    """
    GET / PATCH / DELETE  officer/funding/<id>/

    Officer CRUD on own relief funding requests.
    - Update: mainly while PENDING
    - Delete: PENDING or REJECTED
    """
    permission_classes = OFFICER_PERMS

    def get_obj(self, request, pk):
        try:
            row = ReliefFundingRequest.objects.get(pk=pk)
        except ReliefFundingRequest.DoesNotExist:
            return None, Response({"detail": "তহবিল অনুরোধ পাওয়া যায়নি"}, status=404)
        if row.requested_by_id != request.user.id and not request.user.is_superuser:
            return None, Response({"detail": "এই অনুরোধ আপনার নয়"}, status=403)
        return row, None

    def get(self, request, pk):
        row, err = self.get_obj(request, pk)
        if err:
            return err
        return Response(row.to_dict())

    def patch(self, request, pk):
        row, err = self.get_obj(request, pk)
        if err:
            return err

        # Editable while PENDING / REJECTED / MODIFIED (final APPROVED locked)
        if row.status not in (
            ReliefFundingRequest.Status.PENDING,
            ReliefFundingRequest.Status.REJECTED,
            ReliefFundingRequest.Status.MODIFIED,
        ):
            return Response(
                {
                    "detail": (
                        f"চূড়ান্ত অনুমোদিত অনুরোধ ({row.status}) সম্পাদনা করা যায় না।"
                    )
                },
                status=400,
            )

        data = request.data
        if "incident_name" in data or "incidentName" in data or "title" in data:
            name = (
                data.get("incident_name")
                or data.get("incidentName")
                or data.get("title")
                or ""
            ).strip()
            if name:
                row.incident_name = name

        new_district = row.district
        new_upazila = row.upazila
        if "district" in data and str(data.get("district") or "").strip():
            new_district = str(data.get("district")).strip()
        if "upazila" in data:
            new_upazila = str(data.get("upazila") or "").strip()

        # Location uniqueness (exclude self)
        if new_district != row.district or new_upazila != row.upazila:
            active = (
                ReliefFundingRequest.objects.filter(
                    district__iexact=new_district,
                    upazila__iexact=new_upazila,
                    status__in=[
                        ReliefFundingRequest.Status.PENDING,
                        ReliefFundingRequest.Status.APPROVED,
                        ReliefFundingRequest.Status.MODIFIED,
                    ],
                )
                .exclude(pk=row.pk)
                .first()
            )
            if active:
                return Response(
                    {
                        "detail": (
                            f"এই এলাকায় ইতিমধ্যে সক্রিয় তহবিল আছে (#{active.id})।"
                        )
                    },
                    status=400,
                )
            row.district = new_district
            row.upazila = new_upazila

        if "village" in data:
            row.village = str(data.get("village") or "").strip()
        if "union" in data or "union_name" in data:
            row.union_name = str(data.get("union") or data.get("union_name") or "").strip()
        if "description" in data:
            row.description = str(data.get("description") or "").strip()
        if "note" in data or "officer_note" in data:
            row.officer_note = str(data.get("note") or data.get("officer_note") or "").strip()

        if "amount" in data or "requested_amount" in data:
            try:
                amount = float(data.get("amount") or data.get("requested_amount") or 0)
            except (TypeError, ValueError):
                return Response({"detail": "amount অবৈধ"}, status=400)
            if amount <= 0:
                return Response({"detail": "amount ০ এর বেশি হতে হবে"}, status=400)
            row.requested_amount = amount

        # Re-open REJECTED / MODIFIED → PENDING after officer edit
        if row.status in (
            ReliefFundingRequest.Status.REJECTED,
            ReliefFundingRequest.Status.MODIFIED,
        ):
            row.status = ReliefFundingRequest.Status.PENDING
            row.authority_note = ""
            row.approved_amount = None
            row.decided_by = None
            row.decided_at = None

        row.save()
        return Response(row.to_dict())

    def delete(self, request, pk):
        row, err = self.get_obj(request, pk)
        if err:
            return err
        if row.status not in (
            ReliefFundingRequest.Status.PENDING,
            ReliefFundingRequest.Status.REJECTED,
            ReliefFundingRequest.Status.MODIFIED,
        ):
            return Response(
                {
                    "detail": (
                        f"{row.status} স্ট্যাটাসের অনুরোধ মুছা যায় না। "
                        "শুধু অপেক্ষমাণ/প্রত্যাখ্যাত/সংশোধিত মুছা যাবে।"
                    )
                },
                status=400,
            )
        rid = row.id
        row.delete()
        return Response({"detail": "তহবিল অনুরোধ মুছে ফেলা হয়েছে", "id": rid})


def _district_authorities(district, upazila=None):
    """Local Authority users for a district. বাগেরহাট request → বাগেরহাট authority only."""
    roles = ["LOCAL_AUTHORITY", "AUTHORITY", "UNO", "UPAZILA_NIRBAHI"]
    if not district:
        return list(User.objects.filter(role__in=roles)[:40])

    found = {}
    for u in User.objects.filter(role__in=roles, district__iexact=district)[:40]:
        found[u.pk] = u
    if len(found) < 5:
        for u in User.objects.filter(role__in=roles, district__icontains=district)[:40]:
            found[u.pk] = u

    try:
        from users.models import LocalAuthorityProfile
        pq = LocalAuthorityProfile.objects.filter(user__role__in=roles).select_related(
            "user", "administrative_area", "administrative_area__parent"
        )
        for p in pq[:80]:
            u = p.user
            if u.pk in found:
                continue
            pd = (getattr(p, "district", None) or "").strip()
            if pd and (pd == district or district in pd or pd in district):
                found[u.pk] = u
                continue
            area = getattr(p, "administrative_area", None)
            if not area:
                continue
            names = []
            at = getattr(area, "area_type", None)
            if at == "DISTRICT":
                names.append(area.name)
            elif at == "UPAZILA":
                names.append(area.name)
                parent = getattr(area, "parent", None)
                if parent:
                    names.append(parent.name)
            if any(n and (district == n or district in n or n in district) for n in names):
                found[u.pk] = u
    except Exception:
        pass

    return list(found.values())[:40]


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
        return Response(list_notifications(request.user))


class OfficerNotificationReadAllView(APIView):
    permission_classes = OFFICER_PERMS

    def post(self, request):
        mark_all_read(request.user)
        return Response(list_notifications(request.user))


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
# LOCATION-BASED RESCUE / RELIEF EVENTS
# ============================================================

class OfficerEventListCreateView(APIView):
    """
    GET  officer/events/
    POST officer/events/
      { title, district, upazila?, mission_type: RESCUE|RELIEF, max_volunteers, note? }
    """
    permission_classes = OFFICER_PERMS

    def get(self, request):
        qs = RescueEvent.objects.select_related("created_by").order_by("-created_at")[:100]
        return Response([e.to_dict() for e in qs])

    def post(self, request):
        data = request.data
        title = (data.get("title") or "").strip()
        district = (data.get("district") or "").strip()
        upazila = (data.get("upazila") or "").strip()
        note = (data.get("note") or "").strip()
        mission_type = (data.get("mission_type") or data.get("kind") or "RESCUE").upper()
        if mission_type not in ("RESCUE", "RELIEF"):
            mission_type = "RESCUE"
        try:
            max_v = int(data.get("max_volunteers") or data.get("maxVolunteers") or 10)
        except (TypeError, ValueError):
            return Response({"detail": "max_volunteers অবৈধ"}, status=400)
        if max_v < 1:
            return Response({"detail": "max_volunteers কমপক্ষে ১"}, status=400)
        if not title:
            return Response({"detail": "title আবশ্যক"}, status=400)
        if not district:
            return Response({"detail": "district আবশ্যক"}, status=400)

        ev = RescueEvent.objects.create(
            title=title,
            district=district,
            upazila=upazila,
            mission_type=mission_type,
            max_volunteers=max_v,
            note=note,
            created_by=request.user,
            status=RescueEvent.Status.OPEN,
        )

        # Notify district volunteers
        try:
            peers = _district_volunteers(district, exclude_user=request.user)
            kind_bn = "উদ্ধার" if mission_type == "RESCUE" else "ত্রাণ"
            notify_users(
                peers,
                subject=f"নতুন {kind_bn} ইভেন্ট — {upazila or district}",
                body=(
                    f"{getattr(request.user, 'full_name', request.user)} "
                    f"{kind_bn} ইভেন্ট তৈরি করেছেন: {title}. "
                    f"এলাকা: {upazila}, {district}. "
                    f"সর্বোচ্চ {max_v} জন স্বেচ্ছাসেবক। ড্যাশবোর্ড → উদ্ধার ও ত্রাণ থেকে যোগ দিন।"
                ),
                body_bn="",
                notification_type="assignment",
            )
        except Exception:
            pass

        return Response(ev.to_dict(), status=201)


class OfficerEventDetailView(APIView):
    """
    PATCH officer/events/<pk>/   — edit title, location, max_volunteers, status, note
    DELETE officer/events/<pk>/  — delete event
    """
    permission_classes = OFFICER_PERMS

    def get_obj(self, pk):
        try:
            return RescueEvent.objects.get(pk=pk)
        except RescueEvent.DoesNotExist:
            return None

    def patch(self, request, pk):
        ev = self.get_obj(pk)
        if not ev:
            return Response({"detail": "ইভেন্ট পাওয়া যায়নি"}, status=404)
        data = request.data
        if "title" in data and str(data.get("title") or "").strip():
            ev.title = str(data.get("title")).strip()
        if "district" in data and str(data.get("district") or "").strip():
            ev.district = str(data.get("district")).strip()
        if "upazila" in data:
            ev.upazila = str(data.get("upazila") or "").strip()
        if "note" in data:
            ev.note = str(data.get("note") or "").strip()
        if "mission_type" in data or "kind" in data:
            mt = (data.get("mission_type") or data.get("kind") or "").upper()
            if mt in ("RESCUE", "RELIEF"):
                ev.mission_type = mt
        if "status" in data:
            st = (data.get("status") or "").upper()
            if st in ("OPEN", "CLOSED", "DONE"):
                ev.status = st
        if "max_volunteers" in data or "maxVolunteers" in data:
            try:
                mv = int(data.get("max_volunteers") or data.get("maxVolunteers"))
                if mv < 1:
                    return Response({"detail": "max_volunteers কমপক্ষে ১"}, status=400)
                # cannot set below current joined
                joined = ev.joined_total()
                if mv < joined:
                    return Response(
                        {"detail": f"ইতিমধ্যে {joined} জন যোগ দিয়েছে — max_volunteers কম করা যাবে না"},
                        status=400,
                    )
                ev.max_volunteers = mv
            except (TypeError, ValueError):
                return Response({"detail": "max_volunteers অবৈধ"}, status=400)
        ev.save()
        return Response(ev.to_dict())

    def delete(self, request, pk):
        ev = self.get_obj(pk)
        if not ev:
            return Response({"detail": "ইভেন্ট পাওয়া যায়নি"}, status=404)
        # remove related volunteer activities for this op key
        try:
            from dashboard.models import VolunteerActivity
            VolunteerActivity.objects.filter(operation_key=ev.operation_key).delete()
        except Exception:
            pass
        ev.delete()
        return Response({"detail": "ইভেন্ট মুছে ফেলা হয়েছে", "id": pk})


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
            "funding": self.funding,
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
        verified_qs = incidents.filter(status="verified").order_by("-updated_at")
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_verified = incidents.filter(status="verified", updated_at__gte=today).count()

        def enrich(r):
            row = serialize_report(r)
            vcount = 0
            try:
                vcount = VerificationRecord.objects.filter(
                    incident=r, status="verified"
                ).count()
            except Exception:
                vcount = 1 if (r.status or "").lower() == "verified" else 0
            row["isVerified"] = (r.status or "").lower() == "verified"
            row["verificationCount"] = vcount
            return row

        # Area snapshot: recent incidents with verify status (upazila/district view)
        area_items = [enrich(r) for r in incidents.order_by("-created_at")[:80]]
        verified_items = [enrich(r) for r in verified_qs[:40]]

        return {
            "stats": [
                {"label": "যাচাই অপেক্ষিত", "value": pending_qs.count(), "tone": "amber", "icon": "BadgeCheck"},
                {"label": "যাচাইকৃত (ইভেন্ট যোগ্য)", "value": verified_qs.count(), "tone": "emerald", "icon": "CircleCheck"},
                {"label": "আজ যাচাইকৃত", "value": today_verified, "tone": "lagoon", "icon": "Timer"},
            ],
            "blocks": [
                {
                    "type": "verificationTable",
                    "title": "রিপোর্ট যাচাই (যেকোনো সময় স্ট্যাটাস বদলান)",
                    "items": [serialize_report(r) for r in incidents.order_by("-created_at")[:80]],
                    "hint": "রোতে ক্লিক করে বিস্তারিত দেখুন ও স্ট্যাটাস পরিবর্তন করুন।",
                    "editableStatus": True,
                },
                {
                    "type": "verifiedTable",
                    "title": "যাচাইকৃত রিপোর্ট",
                    "items": verified_items,
                    "hint": "সত্য হিসেবে যাচাইকৃত ঘটনা — ইভেন্ট তৈরি করতে উদ্ধার কার্যক্রম মেনু ব্যবহার করুন।",
                },
                {
                    "type": "areaIncidentTable",
                    "title": "এলাকার সকল ঘটনা (জেলা/উপজেলা)",
                    "items": area_items,
                },
            ],
        }

    def funding(self, user):
        """Officer's location-based funding requests + create form flag."""
        qs = ReliefFundingRequest.objects.filter(requested_by=user).order_by("-created_at")
        pending = qs.filter(status=ReliefFundingRequest.Status.PENDING).count()
        approved = qs.filter(
            status__in=[
                ReliefFundingRequest.Status.APPROVED,
                ReliefFundingRequest.Status.MODIFIED,
            ]
        ).count()
        return {
            "stats": [
                {"label": "অপেক্ষমাণ", "value": pending, "tone": "amber", "icon": "BadgeCheck"},
                {"label": "অনুমোদিত/সংশোধিত", "value": approved, "tone": "emerald", "icon": "CircleCheck"},
                {"label": "মোট অনুরোধ", "value": qs.count(), "tone": "lagoon", "icon": "FileText"},
            ],
            "blocks": [
                {
                    "type": "officerFundingForm",
                    "title": "নতুন ত্রাণ তহবিল অনুরোধ",
                    "hint": "একই জেলা+উপজেলার জন্য একটিমাত্র সক্রিয় তহবিল। ঘটনার নাম ও লোকেশন ম্যানুয়ালি দিন।",
                },
                {
                    "type": "fundingTable",
                    "title": "আমার তহবিল অনুরোধসমূহ",
                    "items": [r.to_dict() for r in qs[:50]],
                    "canManage": True,
                    "readOnly": False,
                },
            ],
        }

    def operations(self, user):
        incidents, *_ = scoped_incidents(user)
        ops = serialize_operations(incidents)
        try:
            events = [
                e.to_dict()
                for e in RescueEvent.objects.select_related("created_by").order_by("-created_at")[:50]
            ]
        except Exception:
            events = []
        merged = events + ops
        running = [o for o in merged if o.get("status") == "IN_PROGRESS"]
        rescued_72 = sum(o.get("rescued") or 0 for o in merged)
        teams = sum(o.get("teams") or 0 for o in running)
        return {
            "stats": [
                {"label": "চলমান অভিযান", "value": len(running), "tone": "red", "icon": "LifeBuoy"},
                {"label": "মোতায়েন দল", "value": teams, "tone": "sky", "icon": "Users"},
                {"label": "উদ্ধারকৃত (৭২ ঘণ্টা)", "value": rescued_72, "tone": "emerald", "icon": "HandHeart"},
            ],
            "blocks": [
                {
                    "type": "officerEventForm",
                    "title": "নতুন উদ্ধার/ত্রাণ ইভেন্ট",
                    "hint": "জেলা-উপজেলা বেছে ইভেন্ট তৈরি করুন। সেই জেলার স্বেচ্ছাসেবক যোগ দিতে পারবে (সর্বোচ্চ সংখ্যা পর্যন্ত)।",
                },
                {
                    "type": "operationCards",
                    "title": "উদ্ধার অভিযানসমূহ",
                    "items": merged,
                    "canManage": True,
                },
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