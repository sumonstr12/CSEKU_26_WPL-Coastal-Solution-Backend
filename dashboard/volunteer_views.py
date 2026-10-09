"""
Community Volunteer dashboard API.

Frontend (VolunteerDashboard + section pages) expects these shapes.
Mount under /api/.../dashboard/

GET  volunteer/overview/
GET  volunteer/badges/
GET  volunteer/reports/
GET  volunteer/shelters/
GET  volunteer/map/
GET  volunteer/profile/
GET  volunteer/section/<key>/   key = community-reports | assistance | my-area
GET  volunteer/availability/
POST volunteer/availability/    { "status": "AVAILABLE"|"UNAVAILABLE" }
POST volunteer/tasks/<pk>/complete/
"""

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.models import ResponderAvailabilityLog
from dashboard.notification_service import unread_count
from dashboard.officer_views import (
    MAP_DISTRICTS,
    district_risk_rows,
    matching_alerts,
    ms,
    serialize_alert_card,
    serialize_report,
    serialize_shelter,
    scoped_shelters,
)
from incidents.models import IncidentReport, ResponseAction, ResponseAssignment, Shelter
from users.models import AdministrativeArea

try:
    from users.models import CommunityVolunteerProfile
except ImportError:  # pragma: no cover
    CommunityVolunteerProfile = None

try:
    from users.models import VolunteerProfile
except ImportError:  # pragma: no cover
    VolunteerProfile = None

try:
    from users.permissions import isCommunityVolunteer
except ImportError:  # pragma: no cover
    isCommunityVolunteer = None


class IsCommunityVolunteer(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if isCommunityVolunteer is not None:
            try:
                return bool(isCommunityVolunteer(user))
            except Exception:
                pass
        role = (getattr(user, "role", None) or "").upper()
        return role in ("COMMUNITY_VOLUNTEER", "VOLUNTEER")


PERMS = [IsAuthenticated, IsCommunityVolunteer]

OPEN_STATUSES = ["submitted", "under_review", "verified", "assigned", "in_progress"]
PENDING_STATUSES = ["submitted", "under_review"]

ASSIGN_TO_TASK = {
    "pending": "PENDING",
    "accepted": "ONGOING",
    "in_progress": "ONGOING",
    "completed": "DONE",
}

BN_DUE = {
    "PENDING": "শীঘ্রই",
    "ONGOING": "চলমান",
    "DONE": "সম্পন্ন",
}


def volunteer_profile(user):
    if CommunityVolunteerProfile is not None:
        p = (
            CommunityVolunteerProfile.objects
            .filter(user=user)
            .prefetch_related("administrative_areas", "administrative_areas__parent")
            .first()
        )
        if p:
            return p
    if VolunteerProfile is not None:
        return (
            VolunteerProfile.objects
            .filter(user=user)
            .prefetch_related("administrative_areas", "administrative_areas__parent")
            .first()
        )
    return None


def scope_parts(user):
    """Return (profile, region_name, district_names, upazila_names)."""
    profile = volunteer_profile(user)
    districts, upazilas = [], []

    if profile and hasattr(profile, "administrative_areas"):
        for area in profile.administrative_areas.all():
            if area.area_type == "DISTRICT":
                districts.append(area.name)
            elif area.area_type == "UPAZILA":
                upazilas.append(area.name)
                if area.parent_id and getattr(area.parent, "area_type", None) == "DISTRICT":
                    districts.append(area.parent.name)
            elif area.area_type == "DIVISION":
                districts.extend(
                    list(area.children.filter(area_type="DISTRICT").values_list("name", flat=True))
                )
            elif area.area_type == "UNION" and area.parent_id:
                upazilas.append(area.parent.name)

    # Single FK style profile (like officer)
    area = getattr(profile, "administrative_area", None) if profile else None
    if area:
        if area.area_type == "UPAZILA":
            upazilas.append(area.name)
            if area.parent_id:
                districts.append(area.parent.name)
        elif area.area_type == "DISTRICT":
            districts.append(area.name)
        elif area.area_type == "DIVISION":
            districts.extend(
                list(area.children.filter(area_type="DISTRICT").values_list("name", flat=True))
            )

    districts = list(dict.fromkeys([d for d in districts if d]))
    upazilas = list(dict.fromkeys([u for u in upazilas if u]))

    if not districts and getattr(user, "district", None):
        districts = [user.district]
    if not upazilas and getattr(user, "upazila", None):
        upazilas = [user.upazila]

    if upazilas and len(upazilas) == 1:
        region = upazilas[0]
    elif districts and len(districts) == 1:
        region = f"{districts[0]} জেলা"
    elif districts:
        region = f"{districts[0]} ও অন্যান্য"
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
    return qs, profile, region, districts, upazilas


def place_of(incident):
    parts = [getattr(incident, "village", None), incident.upazila, incident.district]
    text = ", ".join([p for p in parts if p])
    return text or getattr(incident, "address", None) or ""


def due_label(dt):
    if not dt:
        return "শীঘ্রই"
    now = timezone.now()
    if dt.date() == now.date():
        hour = dt.hour
        period = "সকাল" if hour < 12 else ("বিকাল" if hour < 17 else "সন্ধ্যা")
        h12 = hour % 12 or 12
        return f"আজ {period} {h12}টা"
    if dt.date() == (now + timedelta(days=1)).date():
        return "আগামীকাল"
    return dt.strftime("%d/%m")


def build_tasks(user, limit=20):
    """
    Assistance tasks for the volunteer.

    Prefer ResponseAssignment linked to this user (via assigned_to.user or
    assigned_to matching volunteer profile). Fallback: open area incidents
    as community-assistance opportunities.
    """
    incidents, profile, region, districts, upazilas = scoped_incidents(user)
    tasks = []

    # Assignments where assigned responder/volunteer user matches
    assign_qs = (
        ResponseAssignment.objects
        .select_related("incident", "incident__category", "assigned_to", "assigned_to__user")
        .filter(incident__in=incidents)
        .exclude(status__in=["declined", "cancelled"])
        .order_by("-created_at")
    )

    mine = []
    for a in assign_qs[:50]:
        assignee_user = getattr(getattr(a, "assigned_to", None), "user", None)
        if assignee_user and assignee_user.id == user.id:
            mine.append(a)
        elif profile and getattr(a, "assigned_to_id", None) == getattr(profile, "id", None):
            mine.append(a)

    for a in mine[:limit]:
        inc = a.incident
        status = ASSIGN_TO_TASK.get((a.status or "").lower(), "PENDING")
        title = (
            inc.title_bn or inc.title
            or (inc.category.name_bn if inc.category_id else f"সহায়তা #{inc.id}")
        )
        tasks.append({
            "id": f"ASG-{a.id}",
            "title": title,
            "place": place_of(inc),
            "due": due_label(a.assignment_time or a.created_at) if status != "DONE" else "সম্পন্ন",
            "status": status,
            "detail": (inc.description_bn or inc.description or "")[:160],
            "_assignment_id": a.id,
            "_incident_id": inc.id,
        })

    if tasks:
        return tasks

    # Fallback: area open incidents as suggested assistance work
    open_qs = (
        incidents
        .filter(status__in=OPEN_STATUSES)
        .order_by("-created_at")[:limit]
    )
    for inc in open_qs:
        # completed marker via ResponseAction by this user
        done = ResponseAction.objects.filter(
            assignment__incident=inc,
            performed_by=user,
            action_type__in=["assistance", "relief", "community", "other"],
        ).exists() if hasattr(ResponseAction, "performed_by") else False

        # also check note-based completion
        if not done:
            done = ResponseAction.objects.filter(
                assignment__incident=inc,
                notes__icontains=f"volunteer:{user.id}:done",
            ).exists()

        status = "DONE" if done else ("ONGOING" if inc.status == "in_progress" else "PENDING")
        title = (
            inc.title_bn or inc.title
            or (inc.category.name_bn if inc.category_id else f"সহায়তা #{inc.id}")
        )
        tasks.append({
            "id": f"INC-{inc.id}",
            "title": title,
            "place": place_of(inc),
            "due": BN_DUE.get(status, "শীঘ্রই"),
            "status": status,
            "detail": (inc.description_bn or inc.description or "")[:160],
            "_incident_id": inc.id,
        })

    return tasks


def affected_people_sum(incidents):
    total = (
        incidents.filter(status__in=OPEN_STATUSES)
        .aggregate(s=Sum("affected_people_estimate"))["s"]
        or 0
    )
    return total


def build_activities(user, limit=8):
    incidents, *_ = scoped_incidents(user)
    items = []

    recent = incidents.order_by("-created_at")[:limit]
    for r in recent:
        title = r.title_bn or r.title or f"রিপোর্ট #{r.id}"
        items.append({
            "id": f"r-{r.id}",
            "title": f"কমিউনিটি রিপোর্ট: {title}",
            "time": ms(r.created_at),
            "tone": "lagoon",
            "icon": "FileText",
        })

    actions = (
        ResponseAction.objects
        .filter(assignment__incident__in=incidents)
        .select_related("assignment", "assignment__incident")
        .order_by("-created_at")[:limit]
    )
    for a in actions:
        inc = a.assignment.incident
        title = inc.title_bn or inc.title or f"#{inc.id}"
        items.append({
            "id": f"act-{a.id}",
            "title": f"সহায়তা কার্যক্রম: {title}",
            "time": ms(a.created_at),
            "tone": "emerald",
            "icon": "HandHeart",
        })

    items.sort(key=lambda x: x.get("time") or 0, reverse=True)
    return items[:limit]


# ============================================================
# OVERVIEW
# ============================================================

class VolunteerOverviewView(APIView):
    """Shape expected by VolunteerDashboard.jsx"""
    permission_classes = PERMS

    def get(self, request):
        user = request.user
        now = timezone.now()
        incidents, profile, region, districts, upazilas = scoped_incidents(user)

        alerts = matching_alerts(districts, upazilas[0] if upazilas else None)
        alert = serialize_alert_card(alerts[0]) if alerts else None

        open_count = incidents.filter(status__in=OPEN_STATUSES).count()
        pending_count = incidents.filter(status__in=PENDING_STATUSES).count()
        tasks = build_tasks(user)
        open_tasks = sum(1 for t in tasks if t["status"] != "DONE")
        people = affected_people_sum(incidents)

        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        new_today = incidents.filter(created_at__gte=today).count()

        district_label = districts[0] if districts else region
        upazila_label = upazilas[0] if upazilas else ""

        shelters_qs = scoped_shelters(districts, upazilas[0] if upazilas else None)
        shelter_count = shelters_qs.count()

        # peer volunteers in same area (best-effort)
        volunteer_count = 0
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            vq = User.objects.filter(role="COMMUNITY_VOLUNTEER")
            if districts:
                vq = vq.filter(district__in=districts)
            if upazilas:
                vq = vq.filter(upazila__in=upazilas)
            volunteer_count = vq.count()
        except Exception:
            volunteer_count = 0

        community_reports = [
            serialize_report(r)
            for r in incidents.order_by("-created_at")[:5]
        ]

        stats = [
            {
                "key": "incidents",
                "label": "স্থানীয় সক্রিয় ঘটনা",
                "value": open_count,
                "hint": region,
                "tone": "amber",
                "icon": "Activity",
                "delta": {"dir": "up", "label": f"{new_today}টি নতুন আজ"} if new_today else None,
            },
            {
                "key": "pending",
                "label": "অপেক্ষমাণ রিপোর্ট",
                "value": pending_count,
                "hint": "যাচাই প্রয়োজন",
                "tone": "lagoon",
                "icon": "ClipboardList",
            },
            {
                "key": "tasks",
                "label": "নির্ধারিত কার্যক্রম",
                "value": open_tasks,
                "hint": "আপনার জন্য বরাদ্দ",
                "tone": "sky",
                "icon": "ListChecks",
            },
            {
                "key": "people",
                "label": "সহায়তাপ্রয়োজন মানুষ",
                "value": people,
                "hint": "নিবন্ধিত তালিকা অনুযায়ী",
                "tone": "emerald",
                "icon": "HandHeart",
            },
        ]

        # strip None deltas
        for s in stats:
            if s.get("delta") is None:
                s.pop("delta", None)

        return Response({
            "stats": stats,
            "alert": alert,
            "tasks": tasks,
            "communityReports": community_reports,
            "activities": build_activities(user),
            "area": {
                "district": district_label,
                "upazila": upazila_label or district_label,
                "incidents": open_count,
                "shelters": shelter_count,
                "volunteers": volunteer_count,
            },
        })


# ============================================================
# BADGES
# ============================================================

class VolunteerBadgeView(APIView):
    permission_classes = PERMS

    def get(self, request):
        incidents, *_ = scoped_incidents(request.user)
        tasks = build_tasks(request.user)
        open_tasks = sum(1 for t in tasks if t["status"] != "DONE")
        community = incidents.count()
        unread = unread_count(request.user)
        return Response({
            "notifications": unread,
            "reports": community,
            "community": community,
            "assistance": open_tasks,
            "myReports": 0,
            "verification": incidents.filter(status__in=PENDING_STATUSES).count(),
        })


# ============================================================
# REPORTS / SHELTERS / MAP
# ============================================================

class VolunteerReportsView(APIView):
    permission_classes = PERMS

    def get(self, request):
        incidents, *_ = scoped_incidents(request.user)
        rows = [serialize_report(r) for r in incidents.order_by("-created_at")[:200]]
        return Response(rows)


class VolunteerSheltersView(APIView):
    permission_classes = PERMS

    def get(self, request):
        _, _, _, districts, upazilas = scoped_incidents(request.user)
        qs = scoped_shelters(districts, upazilas[0] if upazilas else None).exclude(
            status="MAINTENANCE"
        )
        return Response([serialize_shelter(s) for s in qs])


class VolunteerMapView(APIView):
    permission_classes = PERMS

    def get(self, request):
        incidents, _, _, districts, upazilas = scoped_incidents(request.user)
        upazila = upazilas[0] if upazilas else None
        alerts = matching_alerts(districts, upazila)
        risk = {
            d["district"]: d["risk"]
            for d in district_risk_rows(incidents, districts, alerts)
        }
        reports = [
            serialize_report(r)
            for r in incidents.exclude(
                status__in=["resolved", "closed", "rejected"]
            ).order_by("-created_at")[:200]
        ]
        shelters = [
            serialize_shelter(s)
            for s in scoped_shelters(districts, upazila).exclude(status="CLOSED")
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

class VolunteerProfileView(APIView):
    permission_classes = PERMS

    def get(self, request):
        user = request.user
        tasks = build_tasks(user, limit=50)
        done = sum(1 for t in tasks if t["status"] == "DONE")
        open_t = sum(1 for t in tasks if t["status"] != "DONE")
        # assistance help count ≈ actions by user
        help_count = ResponseAction.objects.filter(
            notes__icontains=f"volunteer:{user.id}"
        ).count()
        return Response({
            "stats": [
                {"label": "সম্পন্ন কার্যক্রম", "value": done, "tone": "emerald", "icon": "CircleCheck"},
                {"label": "নির্ধারিত আছে", "value": open_t, "tone": "amber", "icon": "ClipboardList"},
                {"label": "যাচাই সহায়তা", "value": help_count, "tone": "lagoon", "icon": "BadgeCheck"},
            ],
            "activities": build_activities(user, limit=12),
        })


# ============================================================
# SECTIONS
# ============================================================

class VolunteerSectionView(APIView):
    permission_classes = PERMS

    def get(self, request, key):
        builders = {
            "community-reports": self.community_reports,
            "assistance": self.assistance,
            "my-area": self.my_area,
        }
        fn = builders.get(key)
        if not fn:
            return Response({"stats": [], "blocks": []})
        return Response(fn(request.user))

    def community_reports(self, user):
        incidents, _, region, _, _ = scoped_incidents(user)
        now = timezone.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = incidents.filter(created_at__gte=today).count()
        pending = incidents.filter(status__in=PENDING_STATUSES).count()
        high = incidents.filter(priority__in=["high", "critical"]).exclude(
            status__in=["resolved", "closed", "rejected"]
        ).count()
        rows = [serialize_report(r) for r in incidents.order_by("-created_at")[:100]]
        return {
            "stats": [
                {
                    "label": "আজকের রিপোর্ট",
                    "value": today_count,
                    "tone": "lagoon",
                    "icon": "FileText",
                    "delta": {"dir": "up", "label": f"{today_count}টি নতুন"} if today_count else None,
                },
                {"label": "যাচাই অপেক্ষিত", "value": pending, "tone": "amber", "icon": "BadgeCheck"},
                {"label": "উচ্চ অগ্রাধিকার", "value": high, "tone": "red", "icon": "ShieldAlert"},
            ],
            "blocks": [
                {
                    "type": "reportTable",
                    "title": f"কমিউনিটি রিপোর্ট ({region})",
                    "items": rows,
                }
            ],
        }

    def assistance(self, user):
        tasks = build_tasks(user, limit=50)
        open_t = sum(1 for t in tasks if t["status"] != "DONE")
        ongoing = sum(1 for t in tasks if t["status"] == "ONGOING")
        # this month completed
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        done_month = ResponseAction.objects.filter(
            notes__icontains=f"volunteer:{user.id}:done",
            created_at__gte=month_start,
        ).count()
        done_month = max(done_month, sum(1 for t in tasks if t["status"] == "DONE"))
        return {
            "stats": [
                {"label": "নির্ধারিত কার্যক্রম", "value": open_t, "tone": "lagoon", "icon": "ListChecks"},
                {"label": "চলমান", "value": ongoing, "tone": "amber", "icon": "Activity"},
                {"label": "এ মাসে সম্পন্ন", "value": done_month, "tone": "emerald", "icon": "CircleCheck"},
            ],
            "blocks": [
                {"type": "taskCards", "title": "সহায়তা কার্যক্রম", "items": tasks},
            ],
        }

    def my_area(self, user):
        incidents, _, region, districts, upazilas = scoped_incidents(user)
        upazila = upazilas[0] if upazilas else None
        alerts = matching_alerts(districts, upazila)
        risk_rows = district_risk_rows(incidents, districts, alerts)
        risk = risk_rows[0] if risk_rows else None

        open_incidents = incidents.filter(status__in=OPEN_STATUSES).count()
        shelter_count = scoped_shelters(districts, upazila).count()

        volunteer_count = 0
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            vq = User.objects.filter(role="COMMUNITY_VOLUNTEER")
            if districts:
                vq = vq.filter(district__in=districts)
            if upazilas:
                vq = vq.filter(upazila__in=upazilas)
            volunteer_count = vq.count()
        except Exception:
            pass

        unions = 0
        if upazilas:
            unions = AdministrativeArea.objects.filter(
                area_type="UNION", parent__name__in=upazilas, parent__area_type="UPAZILA"
            ).count()
        elif districts:
            unions = AdministrativeArea.objects.filter(
                area_type="UNION",
                parent__parent__name__in=districts,
            ).count()

        villages = (
            incidents.exclude(village__isnull=True).exclude(village="")
            .values("village").distinct().count()
        )

        recent = [serialize_report(r) for r in incidents.order_by("-created_at")[:5]]

        return {
            "stats": [
                {"label": "সক্রিয় ঘটনা", "value": open_incidents, "tone": "amber", "icon": "Activity"},
                {"label": "আশ্রয়কেন্দ্র", "value": shelter_count, "tone": "sky", "icon": "Warehouse"},
                {"label": "নিবন্ধিত স্বেচ্ছাসেবক", "value": volunteer_count, "tone": "emerald", "icon": "HandHeart"},
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


# ============================================================
# AVAILABILITY
# ============================================================

class VolunteerAvailabilityView(APIView):
    permission_classes = PERMS

    def get(self, request):
        logs = ResponderAvailabilityLog.objects.filter(user=request.user)[:20]
        rows = [
            {"status": log.status, "note": log.note, "time": ms(log.created_at)}
            for log in logs
        ]
        if not rows:
            status = getattr(request.user, "availability", None) or "AVAILABLE"
            profile = volunteer_profile(request.user)
            if profile and hasattr(profile, "availability_status"):
                status = profile.availability_status or status
            rows = [{
                "status": status,
                "note": "বর্তমান অবস্থা",
                "time": ms(timezone.now()),
            }]
        return Response(rows)

    def post(self, request):
        status = (request.data.get("status") or "").upper()
        allowed = {"AVAILABLE", "UNAVAILABLE"}
        if status not in allowed:
            return Response({"detail": "Invalid status"}, status=400)

        note = request.data.get("note") or "স্বেচ্ছাসেবক availability আপডেট"
        ResponderAvailabilityLog.objects.create(
            user=request.user, status=status, note=note
        )

        # Best-effort persist on user / profile
        profile = volunteer_profile(request.user)
        if profile and hasattr(profile, "availability_status"):
            profile.availability_status = status
            profile.save(update_fields=["availability_status"])
        if hasattr(request.user, "availability"):
            try:
                request.user.availability = status
                request.user.save(update_fields=["availability"])
            except Exception:
                pass

        return Response({"status": status})


# ============================================================
# COMPLETE TASK
# ============================================================

class VolunteerCompleteTaskView(APIView):
    permission_classes = PERMS

    def post(self, request, pk):
        """
        pk may be assignment id (ASG-123 → 123) or incident id (INC-45 → 45)
        or plain integer.
        """
        user = request.user
        raw = str(pk)
        assignment_id = None
        incident_id = None

        if raw.upper().startswith("ASG-"):
            try:
                assignment_id = int(raw.split("-", 1)[1])
            except ValueError:
                return Response({"detail": "Invalid task id"}, status=400)
        elif raw.upper().startswith("INC-"):
            try:
                incident_id = int(raw.split("-", 1)[1])
            except ValueError:
                return Response({"detail": "Invalid task id"}, status=400)
        else:
            try:
                n = int(raw)
            except ValueError:
                return Response({"detail": "Invalid task id"}, status=400)
            # Prefer assignment
            if ResponseAssignment.objects.filter(pk=n).exists():
                assignment_id = n
            else:
                incident_id = n

        if assignment_id:
            try:
                assignment = ResponseAssignment.objects.select_related("incident").get(pk=assignment_id)
            except ResponseAssignment.DoesNotExist:
                return Response({"detail": "Task not found"}, status=404)
            assignment.status = "completed"
            assignment.save(update_fields=["status", "updated_at"] if hasattr(assignment, "updated_at") else ["status"])
            ResponseAction.objects.create(
                assignment=assignment,
                action_type="assistance",
                notes=f"volunteer:{user.id}:done",
                personnel_count=1,
            )
            return Response({"id": f"ASG-{assignment_id}", "status": "DONE"})

        # Incident-based task
        incidents, *_ = scoped_incidents(user)
        try:
            incident = incidents.get(pk=incident_id)
        except IncidentReport.DoesNotExist:
            return Response({"detail": "Task not found in your area"}, status=404)

        # Ensure an assignment exists to hang the action on
        assignment = (
            ResponseAssignment.objects
            .filter(incident=incident)
            .exclude(status__in=["declined", "cancelled"])
            .order_by("-created_at")
            .first()
        )
        if not assignment:
            # Create a lightweight assignment if schema allows null assigned_to
            try:
                assignment = ResponseAssignment.objects.create(
                    incident=incident,
                    status="completed",
                )
            except Exception:
                assignment = None

        if assignment:
            ResponseAction.objects.create(
                assignment=assignment,
                action_type="assistance",
                notes=f"volunteer:{user.id}:done",
                personnel_count=1,
            )
            if assignment.status != "completed":
                assignment.status = "completed"
                try:
                    assignment.save(update_fields=["status", "updated_at"])
                except Exception:
                    assignment.save(update_fields=["status"])

        return Response({"id": f"INC-{incident_id}", "status": "DONE"})
