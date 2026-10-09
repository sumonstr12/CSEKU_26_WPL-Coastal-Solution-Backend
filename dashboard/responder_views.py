"""
Responder dashboard API.

Frontend (ResponderDashboard + section pages) expects these shapes.
Mount under /api/.../dashboard/  (same prefix as officer routes).

GET  responder/context/
GET  responder/overview/
GET  responder/badges/
GET  responder/reports/
GET  responder/shelters/
GET  responder/map/
GET  responder/profile/
GET  responder/section/<key>/     key = missions | rescue-requests | rescue-operations | my-area
GET  responder/availability/
POST responder/availability/      { "status": "AVAILABLE"|"ON_MISSION"|"UNAVAILABLE" }
POST responder/requests/<pk>/accept/
POST responder/missions/<pk>/status/   { "status": "IN_PROGRESS"|"DONE" }
"""

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.models import ResponderAvailabilityLog
from dashboard.notification_service import unread_count
from dashboard.officer_views import (
    MAP_DISTRICTS,
    district_risk_rows,
    fe_severity,
    matching_alerts,
    ms,
    serialize_alert_card,
    serialize_operations,
    serialize_report,
    serialize_shelter,
)
from incidents.models import IncidentReport, ResponseAction, ResponseAssignment, Shelter
from users.models import AdministrativeArea, ResponderProfile
from users.permissions import IsResponder


PERMS = [IsAuthenticated, IsResponder]

OPEN_REQUEST_STATUSES = ["submitted", "under_review", "verified"]
ACTIVE_ASSIGNMENT = ["pending", "accepted", "in_progress"]
PRIORITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1}

TYPE_LABEL = {
    "FIELD_OFFICER": "ফিল্ড অফিসার",
    "RESCUE_TEAM": "উদ্ধারকারী দল",
    "MEDICAL_RESPONDER": "মেডিকেল রেসপন্ডার",
    "EMERGENCY_RESPONDER": "জরুরি উদ্ধারকারী",
}

ASSIGN_TO_FE = {
    "pending": "ASSIGNED",
    "accepted": "ASSIGNED",
    "in_progress": "IN_PROGRESS",
    "completed": "DONE",
}

FE_TO_ASSIGN = {
    "IN_PROGRESS": "in_progress",
    "DONE": "completed",
}


def responder_profile(user):
    return (
        ResponderProfile.objects
        .filter(user=user)
        .prefetch_related("administrative_areas", "administrative_areas__parent")
        .first()
    )


def team_label(profile, user):
    if profile and profile.organization:
        return profile.organization
    if profile and profile.responder_type:
        return TYPE_LABEL.get(profile.responder_type, user.full_name)
    return user.full_name


def scope_parts(user):
    """Return (profile, region_name, district_names, upazila_names)."""
    profile = responder_profile(user)
    districts, upazilas = [], []

    if profile:
        for area in profile.administrative_areas.all():
            if area.area_type == "DISTRICT":
                districts.append(area.name)
            elif area.area_type == "UPAZILA":
                upazilas.append(area.name)
                if area.parent_id and area.parent.area_type == "DISTRICT":
                    districts.append(area.parent.name)
            elif area.area_type == "DIVISION":
                districts.extend(
                    area.children.filter(area_type="DISTRICT").values_list("name", flat=True)
                )
            elif area.area_type == "UNION" and area.parent_id:
                upazilas.append(area.parent.name)

    districts = list(dict.fromkeys([d for d in districts if d]))
    upazilas = list(dict.fromkeys([u for u in upazilas if u]))

    if not districts and not upazilas and getattr(user, "district", None):
        districts = [user.district]

    if len(districts) == 1:
        region = f"{districts[0]} জেলা"
    elif districts:
        region = f"{districts[0]} ও অন্যান্য"
    elif upazilas:
        region = upazilas[0]
    else:
        region = "আপনার এলাকা"

    return profile, region, districts, upazilas


def area_q(districts, upazilas):
    q = Q()
    if districts:
        q |= Q(district__in=districts)
    if upazilas:
        q |= Q(upazila__in=upazilas)
    return q


def scoped_incidents(user):
    profile, region, districts, upazilas = scope_parts(user)
    qs = IncidentReport.objects.select_related("category", "reporter")
    q = area_q(districts, upazilas)
    if q:
        qs = qs.filter(q)
    else:
        qs = qs.none()
    return qs, profile, region, districts, upazilas


def my_assignments(user):
    profile = responder_profile(user)
    if not profile:
        return ResponseAssignment.objects.none()
    return (
        ResponseAssignment.objects
        .filter(assigned_to=profile)
        .select_related("incident", "incident__category", "assigned_to", "assigned_to__user")
        .exclude(status__in=["declined", "cancelled"])
    )


def place_of(incident):
    parts = [incident.village, incident.upazila, incident.district]
    text = ", ".join([p for p in parts if p])
    return text or incident.address or ""


def progress_of(assignment, action_count):
    if assignment.status == "completed":
        return 100
    if assignment.status == "in_progress":
        return min(90, 35 + (action_count or 0) * 15)
    if assignment.status == "accepted":
        return 15
    return 0


def serialize_mission(assignment, team, action_count=0):
    incident = assignment.incident
    return {
        "id": assignment.id,
        "title": incident.title_bn or incident.title or f"মিশন #{assignment.id}",
        "place": place_of(incident),
        "type": incident.category.name_bn if incident.category_id else "উদ্ধার",
        "priority": fe_severity(incident),
        "status": ASSIGN_TO_FE.get(assignment.status, "ASSIGNED"),
        "assignedAt": ms(assignment.assignment_time or assignment.created_at),
        "people": incident.affected_people_estimate or None,
        "team": team,
        "progress": progress_of(assignment, action_count),
    }


def serialize_request(incident):
    active = incident.response_assignments.filter(status__in=ACTIVE_ASSIGNMENT).exists()
    contact = incident.reporter_phone or ""
    if not contact and incident.reporter_id and not incident.is_anonymous:
        contact = getattr(incident.reporter, "phone_number", "") or ""
    need = incident.title_bn or incident.title or (incident.description_bn or incident.description or "")[:140]
    return {
        "id": incident.id,
        "place": place_of(incident) or incident.upazila or "",
        "district": incident.district or "",
        "need": need,
        "severity": fe_severity(incident),
        "time": ms(incident.incident_time or incident.created_at),
        "status": "ASSIGNED" if active else "OPEN",
        "contact": contact,
    }


def open_request_qs(incidents):
    taken = ResponseAssignment.objects.filter(
        incident__in=incidents,
        status__in=ACTIVE_ASSIGNMENT,
    ).values("incident_id")
    return (
        incidents
        .filter(is_sos=True, status__in=OPEN_REQUEST_STATUSES)
        .exclude(id__in=taken)
        .order_by("-created_at")
    )


def log_availability(user, status, note):
    ResponderAvailabilityLog.objects.create(user=user, status=status, note=note or "")


def set_availability(user, profile, status, note):
    if not profile:
        return False
    if profile.availability_status != status:
        profile.availability_status = status
        profile.save(update_fields=["availability_status", "updated_at"])
        log_availability(user, status, note)
    return True


def action_counts(assignment_ids):
    if not assignment_ids:
        return {}
    rows = (
        ResponseAction.objects
        .filter(assignment_id__in=assignment_ids)
        .values("assignment_id")
        .annotate(c=Count("id"))
    )
    return {row["assignment_id"]: row["c"] for row in rows}


def missions_payload(user):
    profile, _, _, _ = scope_parts(user)
    team = team_label(profile, user)
    qs = list(my_assignments(user).order_by("-assignment_time"))
    counts = action_counts([a.id for a in qs])
    items = [serialize_mission(a, team, counts.get(a.id, 0)) for a in qs]
    rank = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "LOW": 3}
    items.sort(key=lambda m: (0 if m["status"] != "DONE" else 1, rank.get(m["priority"], 9)))
    return items


def activities_for(user, limit=6):
    items = []
    for action in (
        ResponseAction.objects
        .filter(performed_by=user)
        .select_related("assignment", "assignment__incident")
        .order_by("-action_time")[:limit]
    ):
        incident = action.assignment.incident
        items.append({
            "id": f"act-{action.id}",
            "kind": "mission",
            "title": action.description_bn or action.description,
            "place": place_of(incident),
            "time": ms(action.action_time),
        })
    if len(items) < limit:
        for assignment in my_assignments(user).order_by("-assignment_time")[: limit - len(items)]:
            items.append({
                "id": f"asg-{assignment.id}",
                "kind": "mission",
                "title": assignment.incident.title_bn or assignment.incident.title or "মিশন বরাদ্দ হয়েছে",
                "place": place_of(assignment.incident),
                "time": ms(assignment.assignment_time),
            })
    return items


def require_profile(user):
    profile = responder_profile(user)
    if profile:
        return profile, None
    return None, Response(
        {"detail": "Responder profile পাওয়া যায়নি। অ্যাডমিনকে প্রোফাইল সেট করতে বলুন।"},
        status=400,
    )


class ResponderContextView(APIView):
    """হেডার / availability কার্ডের জন্য team, district, availability।"""

    permission_classes = PERMS

    def get(self, request):
        profile, region, districts, upazilas = scope_parts(request.user)
        return Response({
            "team": team_label(profile, request.user),
            "organization": (profile.organization if profile else "") or "",
            "availability": (profile.availability_status if profile else "AVAILABLE"),
            "responder_type": (profile.responder_type if profile else ""),
            "district": districts[0] if districts else (request.user.district or ""),
            "upazila": upazilas[0] if upazilas else "",
            "region": region,
        })


class ResponderOverviewView(APIView):
    permission_classes = PERMS

    def get(self, request):
        incidents, profile, region, districts, upazilas = scoped_incidents(request.user)
        now = timezone.now()
        year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

        missions = missions_payload(request.user)
        active = [m for m in missions if m["status"] == "IN_PROGRESS"]
        assigned = [m for m in missions if m["status"] == "ASSIGNED"]
        done_year = my_assignments(request.user).filter(
            status="completed",
            updated_at__gte=year_start,
        ).count()

        open_qs = open_request_qs(incidents)
        open_count = open_qs.count()
        new_today = open_qs.filter(created_at__gte=now - timedelta(hours=24)).count()

        critical = incidents.filter(
            priority__in=["high", "critical"],
        ).exclude(status__in=["resolved", "closed", "rejected", "duplicate"]).count()

        alerts = matching_alerts(districts, upazilas[0] if len(upazilas) == 1 else None)
        alert = serialize_alert_card(alerts[0]) if alerts else None

        requests = [serialize_request(r) for r in open_qs[:5]]
        # show a few already-taken ones too, so the list isn't empty after accept
        if len(requests) < 5:
            taken_ids = (
                ResponseAssignment.objects
                .filter(incident__in=incidents, status__in=ACTIVE_ASSIGNMENT)
                .values_list("incident_id", flat=True)[:5]
            )
            extra = incidents.filter(id__in=list(taken_ids), is_sos=True)
            seen = {r["id"] for r in requests}
            for incident in extra:
                if incident.id not in seen:
                    requests.append(serialize_request(incident))
                if len(requests) >= 5:
                    break

        stats = [
            {
                "key": "missions",
                "label": "সক্রিয় মিশন",
                "value": len(active),
                "hint": "এই মুহূর্তে চলমান",
                "tone": "red",
                "icon": "Target",
            },
            {
                "key": "requests",
                "label": "অপেক্ষমাণ জরুরি অনুরোধ",
                "value": open_count,
                "hint": "সাড়া প্রয়োজন",
                "tone": "amber",
                "icon": "Siren",
                "delta": {"dir": "up", "label": f"{new_today}টি নতুন"} if new_today else None,
            },
            {
                "key": "critical",
                "label": "উচ্চ অগ্রাধিকার ঘটনা",
                "value": critical,
                "hint": region,
                "tone": "orange",
                "icon": "ShieldAlert",
            },
            {
                "key": "done",
                "label": "সম্পন্ন মিশন",
                "value": done_year,
                "hint": "চলতি বছরে",
                "tone": "emerald",
                "icon": "CircleCheck",
            },
        ]
        # drop null delta so the card doesn't render an empty pill
        for row in stats:
            if row.get("delta") is None:
                row.pop("delta", None)

        return Response({
            "stats": stats,
            "alert": alert,
            "missions": [m for m in missions if m["status"] != "DONE"] or missions[:4],
            "requests": requests,
            "activities": activities_for(request.user),
            "assignedCount": len(assigned),
        })


class ResponderBadgeView(APIView):
    permission_classes = PERMS

    def get(self, request):
        incidents, _, _, districts, upazilas = scoped_incidents(request.user)
        missions = my_assignments(request.user).exclude(status="completed")
        running = (
            ResponseAssignment.objects
            .filter(incident__in=incidents, status__in=ACTIVE_ASSIGNMENT)
            .values("incident_id")
            .distinct()
            .count()
        )
        alerts = matching_alerts(districts, upazilas[0] if len(upazilas) == 1 else None)
        return Response({
            "notifications": unread_count(request.user),
            "reports": incidents.count(),
            "missions": missions.count(),
            "requests": open_request_qs(incidents).count(),
            "operations": running,
            "monitoring": sum(1 for a in alerts if (a.severity or "").lower() in ("critical", "high")),
        })


class ResponderReportsView(APIView):
    permission_classes = PERMS

    def get(self, request):
        incidents, *_ = scoped_incidents(request.user)
        rows = [serialize_report(r) for r in incidents.order_by("-created_at")[:200]]
        for row in rows:
            if row.get("time") is not None and not isinstance(row["time"], (int, float)):
                row["time"] = ms(row["time"])
            if row.get("incident_time") is not None and not isinstance(row["incident_time"], (int, float)):
                row["incident_time"] = ms(row["incident_time"])
        return Response(rows)


class ResponderSheltersView(APIView):
    permission_classes = PERMS

    def get(self, request):
        _, _, _, districts, upazilas = scoped_incidents(request.user)
        qs = Shelter.objects.filter(is_active=True).exclude(status="MAINTENANCE")
        q = area_q(districts, upazilas)
        if q:
            qs = qs.filter(q)
        else:
            qs = qs.none()
        return Response([serialize_shelter(s) for s in qs])


class ResponderMapView(APIView):
    permission_classes = PERMS

    def get(self, request):
        incidents, _, _, districts, upazilas = scoped_incidents(request.user)
        alerts = matching_alerts(districts, upazilas[0] if len(upazilas) == 1 else None)
        risk = {d["district"]: d["risk"] for d in district_risk_rows(incidents, districts, alerts)}
        reports = []
        for r in incidents.exclude(status__in=["resolved", "closed", "rejected"]).order_by("-created_at")[:200]:
            row = serialize_report(r)
            if row.get("time") is not None and not isinstance(row["time"], (int, float)):
                row["time"] = ms(row["time"])
            reports.append(row)
        shelters_qs = Shelter.objects.filter(is_active=True).exclude(status="CLOSED")
        q = area_q(districts, upazilas)
        if q:
            shelters_qs = shelters_qs.filter(q)
        else:
            shelters_qs = shelters_qs.none()
        return Response({
            "reports": reports,
            "shelters": [serialize_shelter(s) for s in shelters_qs],
            "activeDisasters": [serialize_alert_card(a) for a in alerts],
            "mapDistricts": [
                {**d, "risk": risk.get(d["name"], 0)}
                for d in MAP_DISTRICTS
            ],
        })


class ResponderProfileView(APIView):
    permission_classes = PERMS

    def get(self, request):
        now = timezone.now()
        year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        assignments = my_assignments(request.user)
        done = assignments.filter(status="completed", updated_at__gte=year_start).count()
        active = assignments.filter(status="in_progress").count()
        rescued = (
            ResponseAction.objects
            .filter(
                performed_by=request.user,
                action_type__in=["rescue", "evacuation"],
                action_time__gte=year_start,
            )
            .aggregate(total=Sum("personnel_count"))["total"]
            or 0
        )
        return Response({
            "stats": [
                {"label": "সম্পন্ন মিশন", "value": done, "tone": "emerald", "icon": "CircleCheck"},
                {"label": "সক্রিয় মিশন", "value": active, "tone": "red", "icon": "Target"},
                {"label": "উদ্ধার (চলতি বছর)", "value": rescued, "tone": "sky", "icon": "LifeBuoy"},
            ],
            "activities": activities_for(request.user),
        })


class ResponderSectionView(APIView):
    permission_classes = PERMS

    def get(self, request, key):
        builders = {
            "missions": self.missions,
            "rescue-requests": self.requests,
            "rescue-operations": self.operations,
            "my-area": self.my_area,
        }
        fn = builders.get(key)
        if not fn:
            return Response({"stats": [], "blocks": []})
        return Response(fn(request.user))

    def missions(self, user):
        items = missions_payload(user)
        return {
            "stats": [
                {"label": "সক্রিয় মিশন", "value": sum(1 for m in items if m["status"] == "IN_PROGRESS"), "tone": "red", "icon": "Target"},
                {"label": "বরাদ্দকৃত", "value": sum(1 for m in items if m["status"] == "ASSIGNED"), "tone": "amber", "icon": "ClipboardList"},
                {"label": "সম্পন্ন", "value": sum(1 for m in items if m["status"] == "DONE"), "tone": "emerald", "icon": "CircleCheck"},
            ],
            "blocks": [{"type": "missionCards", "title": "আপনার মিশনসমূহ", "items": items}],
        }

    def requests(self, user):
        incidents, *_ = scoped_incidents(user)
        open_rows = [serialize_request(r) for r in open_request_qs(incidents)[:40]]
        assigned_ids = (
            ResponseAssignment.objects
            .filter(incident__in=incidents, status__in=ACTIVE_ASSIGNMENT)
            .values_list("incident_id", flat=True)[:40]
        )
        assigned_rows = [
            serialize_request(r)
            for r in incidents.filter(id__in=list(assigned_ids), is_sos=True)
        ]
        seen = set()
        items = []
        for row in open_rows + assigned_rows:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            items.append(row)
        items.sort(key=lambda r: PRIORITY_RANK.get(r["severity"], 0), reverse=True)
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        done_today = my_assignments(user).filter(status="completed", updated_at__gte=today).count()
        return {
            "stats": [
                {"label": "খোলা অনুরোধ", "value": sum(1 for r in items if r["status"] == "OPEN"), "tone": "red", "icon": "Siren"},
                {"label": "বরাদ্দকৃত", "value": sum(1 for r in items if r["status"] == "ASSIGNED"), "tone": "amber", "icon": "UserCheck"},
                {"label": "আজ সম্পন্ন", "value": done_today, "tone": "emerald", "icon": "CircleCheck"},
            ],
            "blocks": [{"type": "requestCards", "title": "জরুরি অনুরোধসমূহ", "items": items}],
        }

    def operations(self, user):
        incidents, *_ = scoped_incidents(user)
        ops = serialize_operations(incidents)
        for op in ops:
            if op.get("startedAt") is not None and not isinstance(op["startedAt"], (int, float)):
                op["startedAt"] = ms(op["startedAt"])
        running = [o for o in ops if o["status"] == "IN_PROGRESS"]
        return {
            "stats": [
                {"label": "চলমান অভিযান", "value": len(running), "tone": "red", "icon": "LifeBuoy"},
                {"label": "মোতায়েন দল", "value": sum(o["teams"] for o in running), "tone": "sky", "icon": "Users"},
                {"label": "উদ্ধারকৃত (৭২ ঘণ্টা)", "value": sum(o["rescued"] for o in ops), "tone": "emerald", "icon": "HandHeart"},
            ],
            "blocks": [{"type": "operationCards", "title": "উদ্ধার অভিযানসমূহ", "items": ops}],
        }

    def my_area(self, user):
        incidents, _, region, districts, upazilas = scoped_incidents(user)
        alerts = matching_alerts(districts, upazilas[0] if len(upazilas) == 1 else None)
        risk_rows = district_risk_rows(incidents, districts, alerts)
        risk = risk_rows[0] if risk_rows else None

        if upazilas:
            unions = AdministrativeArea.objects.filter(
                area_type="UNION", parent__name__in=upazilas, parent__area_type="UPAZILA"
            ).count()
        elif districts:
            unions = AdministrativeArea.objects.filter(
                area_type="UNION",
                parent__parent__name__in=districts,
            ).count()
        else:
            unions = 0

        villages = (
            incidents.exclude(village__isnull=True).exclude(village="")
            .values("village").distinct().count()
        )
        shelter_count = Shelter.objects.filter(is_active=True)
        q = area_q(districts, upazilas)
        if q:
            shelter_count = shelter_count.filter(q)
        else:
            shelter_count = shelter_count.none()
        open_incidents = incidents.exclude(status__in=["resolved", "closed", "rejected", "duplicate"]).count()

        recent = []
        for r in incidents.order_by("-created_at")[:5]:
            row = serialize_report(r)
            if row.get("time") is not None and not isinstance(row["time"], (int, float)):
                row["time"] = ms(row["time"])
            recent.append(row)

        return {
            "stats": [
                {"label": "সক্রিয় ঘটনা", "value": open_incidents, "tone": "amber", "icon": "Activity"},
                {"label": "আশ্রয়কেন্দ্র", "value": shelter_count.count(), "tone": "sky", "icon": "Warehouse"},
                {"label": "আমার মিশন", "value": my_assignments(user).exclude(status="completed").count(), "tone": "emerald", "icon": "LifeBuoy"},
            ],
            "blocks": [
                {
                    "type": "areaPanel",
                    "title": region,
                    "subtitle": "আপনার দায়িত্বপূর্ণ এলাকা",
                    "area": {
                        "unions": unions,
                        "villages": villages,
                        "population": "—",
                        "risk": risk,
                    },
                },
                {"type": "reportTable", "title": "এলাকার সাম্প্রতিক রিপোর্ট", "items": recent},
            ],
        }


class ResponderAvailabilityView(APIView):
    permission_classes = PERMS

    def get(self, request):
        logs = ResponderAvailabilityLog.objects.filter(user=request.user)[:20]
        rows = [
            {"status": log.status, "note": log.note, "time": ms(log.created_at)}
            for log in logs
        ]
        if not rows:
            profile = responder_profile(request.user)
            rows = [{
                "status": profile.availability_status if profile else "AVAILABLE",
                "note": "বর্তমান অবস্থা",
                "time": ms(timezone.now()),
            }]
        return Response(rows)

    def post(self, request):
        status = (request.data.get("status") or "").upper()
        allowed = {"AVAILABLE", "ON_MISSION", "UNAVAILABLE"}
        if status not in allowed:
            return Response({"detail": "Invalid status"}, status=400)
        profile, error = require_profile(request.user)
        if error:
            return error
        note = request.data.get("note") or "নিজে থেকে আপডেট করা হয়েছে"
        set_availability(request.user, profile, status, note)
        return Response({"status": status})


class ResponderAcceptRequestView(APIView):
    permission_classes = PERMS

    def post(self, request, pk):
        profile, error = require_profile(request.user)
        if error:
            return error

        incidents, *_ = scoped_incidents(request.user)
        try:
            incident = incidents.get(pk=pk)
        except IncidentReport.DoesNotExist:
            return Response({"detail": "অনুরোধ আপনার এলাকায় নেই, বা খুঁজে পাওয়া যায়নি।"}, status=404)

        existing = (
            ResponseAssignment.objects
            .filter(incident=incident, status__in=ACTIVE_ASSIGNMENT)
            .select_related("assigned_to")
            .first()
        )
        if existing and existing.assigned_to_id != profile.id:
            return Response({"detail": "এই অনুরোধ অন্য উদ্ধারকারীর কাছে বরাদ্দ হয়েছে।"}, status=409)

        if incident.status in ("resolved", "closed", "rejected", "duplicate") and not existing:
            return Response({"detail": "এই অনুরোধ আর খোলা নেই।"}, status=400)

        fresh = False
        if not existing:
            existing = ResponseAssignment.objects.create(
                incident=incident,
                assigned_to=profile,
                assigned_by=request.user,
                status="accepted",
                instructions=incident.description_bn or incident.description or "",
            )
            if incident.status in OPEN_REQUEST_STATUSES:
                incident.status = "assigned"
                incident.save(update_fields=["status", "updated_at"])
            fresh = True
        elif existing.status == "pending":
            existing.status = "accepted"
            existing.save(update_fields=["status", "updated_at"])
            fresh = True

        if fresh:
            set_availability(request.user, profile, "ON_MISSION", f"অনুরোধ #{incident.id} গ্রহণ")
            ResponseAction.objects.create(
                assignment=existing,
                performed_by=request.user,
                action_type="communication",
                description=f"Rescue request #{incident.id} accepted",
                description_bn="জরুরি অনুরোধ গ্রহণ করা হয়েছে",
            )
        return Response(serialize_request(incident))


class ResponderMissionStatusView(APIView):
    permission_classes = PERMS

    def post(self, request, pk):
        wanted = (request.data.get("status") or "").upper()
        if wanted not in FE_TO_ASSIGN:
            return Response({"detail": "status must be IN_PROGRESS or DONE"}, status=400)

        profile, error = require_profile(request.user)
        if error:
            return error

        try:
            assignment = my_assignments(request.user).get(pk=pk)
        except ResponseAssignment.DoesNotExist:
            return Response({"detail": "মিশন পাওয়া যায়নি।"}, status=404)

        assignment.status = FE_TO_ASSIGN[wanted]
        assignment.save(update_fields=["status", "updated_at"])

        if wanted == "IN_PROGRESS":
            if assignment.incident.status in OPEN_REQUEST_STATUSES + ["assigned"]:
                assignment.incident.status = "in_progress"
                assignment.incident.save(update_fields=["status", "updated_at"])
            set_availability(request.user, profile, "ON_MISSION", f"মিশন #{assignment.id} শুরু")
            ResponseAction.objects.create(
                assignment=assignment,
                performed_by=request.user,
                action_type="arrived",
                description="Mission started",
                description_bn="মিশন শুরু করা হয়েছে",
            )
        else:
            still_open = my_assignments(request.user).filter(status__in=ACTIVE_ASSIGNMENT).exclude(pk=assignment.pk).exists()
            others = assignment.incident.response_assignments.filter(status__in=ACTIVE_ASSIGNMENT).exists()
            if not others:
                assignment.incident.status = "resolved"
                assignment.incident.save(update_fields=["status", "updated_at"])
            if not still_open:
                set_availability(request.user, profile, "AVAILABLE", f"মিশন #{assignment.id} সম্পন্ন")
            ResponseAction.objects.create(
                assignment=assignment,
                performed_by=request.user,
                action_type="resolution",
                description="Mission completed",
                description_bn="মিশন সম্পন্ন করা হয়েছে",
            )

        team = team_label(profile, request.user)
        count = assignment.response_actions.count()
        return Response(serialize_mission(assignment, team, count))
