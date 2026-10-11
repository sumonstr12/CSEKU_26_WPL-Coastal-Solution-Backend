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
GET  volunteer/section/<key>/   key = community-reports | assistance | my-area | rescue-operations
GET  volunteer/availability/
POST volunteer/availability/    { "status": "AVAILABLE"|"UNAVAILABLE" }
POST volunteer/tasks/<pk>/complete/   optional body: note, people_helped
POST volunteer/tasks/<pk>/update/     { status?, note?, people_helped?, detail? }
GET  volunteer/operations/
POST volunteer/operations/<key>/join/  { kind?: RELIEF|RESCUE, note? }
GET  volunteer/activities/
"""

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.contrib.auth import get_user_model

from dashboard.models import ResponderAvailabilityLog, VolunteerActivity
from dashboard.notification_service import notify_users, unread_count
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

User = get_user_model()

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


def _safe_profile_qs(model, user):
    """
    Load profile without assuming relation names.
    CommunityVolunteerProfile may use administrative_area (FK) or
    district/upazila text fields — NOT administrative_areas M2M.
    """
    qs = model.objects.filter(user=user)
    field_names = {f.name for f in model._meta.get_fields()}

    # Single FK (officer-style)
    if "administrative_area" in field_names:
        qs = qs.select_related("administrative_area", "administrative_area__parent")
    # M2M (responder-style) — only if the field really exists
    elif "administrative_areas" in field_names:
        qs = qs.prefetch_related("administrative_areas", "administrative_areas__parent")

    return qs.first()


def volunteer_profile(user):
    if CommunityVolunteerProfile is not None:
        p = _safe_profile_qs(CommunityVolunteerProfile, user)
        if p:
            return p
    if VolunteerProfile is not None:
        return _safe_profile_qs(VolunteerProfile, user)
    return None


def _collect_area(area, districts, upazilas):
    if not area:
        return
    at = getattr(area, "area_type", None)
    if at == "DISTRICT":
        districts.append(area.name)
    elif at == "UPAZILA":
        upazilas.append(area.name)
        parent = getattr(area, "parent", None)
        if parent and getattr(parent, "area_type", None) == "DISTRICT":
            districts.append(parent.name)
        elif area.parent_id:
            try:
                districts.append(area.parent.name)
            except Exception:
                pass
    elif at == "DIVISION":
        try:
            districts.extend(
                list(area.children.filter(area_type="DISTRICT").values_list("name", flat=True))
            )
        except Exception:
            pass
    elif at == "UNION" and area.parent_id:
        try:
            upazilas.append(area.parent.name)
        except Exception:
            pass


def scope_parts(user):
    """Return (profile, region_name, district_names, upazila_names)."""
    profile = volunteer_profile(user)
    districts, upazilas = [], []

    if profile:
        field_names = {f.name for f in profile._meta.get_fields()}

        # M2M administrative_areas
        if "administrative_areas" in field_names:
            try:
                for area in profile.administrative_areas.all():
                    _collect_area(area, districts, upazilas)
            except Exception:
                pass

        # Single FK administrative_area
        if "administrative_area" in field_names:
            _collect_area(getattr(profile, "administrative_area", None), districts, upazilas)

        # Plain text fields on profile
        for attr, bucket in (
            ("district", districts),
            ("upazila", upazilas),
            ("assigned_district", districts),
            ("assigned_upazila", upazilas),
        ):
            if attr in field_names:
                val = getattr(profile, attr, None)
                if val and isinstance(val, str):
                    bucket.append(val)

    districts = list(dict.fromkeys([d for d in districts if d]))
    upazilas = list(dict.fromkeys([u for u in upazilas if u]))

    # Fallback: custom User model fields
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


def build_tasks(user, limit=30):
    """
    Assistance + relief/rescue activities for the volunteer.

    1) Persisted VolunteerActivity rows (joined ops, updated help logs)
    2) ResponseAssignment linked to this user
    3) Open area incidents as suggested assistance (if not already tracked)
    """
    incidents, profile, region, districts, upazilas = scoped_incidents(user)
    tasks = []
    seen_incident = set()
    seen_asg = set()

    # 1) Own VolunteerActivity records
    for act in VolunteerActivity.objects.filter(user=user).order_by("-updated_at")[:limit]:
        row = act.to_task_dict()
        tasks.append(row)
        if act.incident_id:
            seen_incident.add(act.incident_id)
        if act.assignment_id:
            seen_asg.add(act.assignment_id)

    # 2) Assignments assigned to this user
    assign_qs = (
        ResponseAssignment.objects
        .select_related("incident", "incident__category", "assigned_to", "assigned_to__user")
        .filter(incident__in=incidents)
        .exclude(status__in=["declined", "cancelled"])
        .order_by("-created_at")
    )
    mine = []
    for a in assign_qs[:50]:
        if a.id in seen_asg:
            continue
        assignee_user = getattr(getattr(a, "assigned_to", None), "user", None)
        if assignee_user and assignee_user.id == user.id:
            mine.append(a)
        elif profile and getattr(a, "assigned_to_id", None) == getattr(profile, "id", None):
            mine.append(a)

    for a in mine:
        if len(tasks) >= limit:
            break
        inc = a.incident
        status = ASSIGN_TO_TASK.get((a.status or "").lower(), "PENDING")
        # Prefer VolunteerActivity status if later synced — already skipped via seen_asg
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
            "note": "",
            "kind": "ASSISTANCE",
            "peopleHelped": 0,
            "incidentId": inc.id,
        })
        seen_incident.add(inc.id)
        seen_asg.add(a.id)

    # 3) Suggested open incidents not yet tracked
    open_qs = (
        incidents
        .filter(status__in=OPEN_STATUSES)
        .order_by("-created_at")[:limit]
    )
    for inc in open_qs:
        if len(tasks) >= limit:
            break
        if inc.id in seen_incident:
            continue
        done = ResponseAction.objects.filter(
            assignment__incident=inc,
            notes__icontains=f"volunteer:{user.id}:done",
        ).exists()
        # Also covered if VA exists — already in seen_incident
        status = "DONE" if done else ("ONGOING" if inc.status == "in_progress" else "PENDING")
        title = (
            inc.title_bn or inc.title
            or (inc.category.name_bn if inc.category_id else f"সহায়তা #{inc.id}")
        )
        people = inc.affected_people_estimate or 0
        tasks.append({
            "id": f"INC-{inc.id}",
            "title": title,
            "place": place_of(inc),
            "due": BN_DUE.get(status, "শীঘ্রই"),
            "status": status,
            "detail": (inc.description_bn or inc.description or "")[:160],
            "note": "",
            "kind": "ASSISTANCE",
            "peopleHelped": 0,
            "suggestedPeople": people,
            "incidentId": inc.id,
        })

    return tasks


def build_operations_for_volunteer(user):
    """Area rescue/relief operations with join state for this volunteer."""
    incidents, profile, region, districts, upazilas = scoped_incidents(user)
    ops = serialize_operations(incidents)

    # Officer-created location events for volunteer's district
    try:
        from dashboard.models import RescueEvent
        eq = RescueEvent.objects.filter(status=RescueEvent.Status.OPEN).select_related("created_by")
        if districts:
            from django.db.models import Q
            q = Q()
            for d in districts:
                q |= Q(district__iexact=d) | Q(district__icontains=d)
            # also user.district
            ud = getattr(user, "district", None)
            if ud:
                q |= Q(district__iexact=ud) | Q(district__icontains=ud)
            eq = eq.filter(q)
        else:
            ud = getattr(user, "district", None)
            if ud:
                eq = eq.filter(district__icontains=ud)
        for e in eq.order_by("-created_at")[:40]:
            ops.insert(0, e.to_dict())
    except Exception:
        pass

    joined_keys = set(
        VolunteerActivity.objects.filter(
            user=user,
            operation_key__gt="",
        ).exclude(status="DONE").values_list("operation_key", flat=True)
    )
    joined_done = set(
        VolunteerActivity.objects.filter(
            user=user,
            operation_key__gt="",
            status="DONE",
        ).values_list("operation_key", flat=True)
    )
    out = []
    for o in ops:
        key = str(o.get("id") or "")
        can_join = o.get("canJoin", True)
        if o.get("isLocationEvent") and o.get("canJoin") is False:
            can_join = False
        row = {
            **o,
            "canJoin": can_join and key not in joined_keys and key not in joined_done,
            "joined": key in joined_keys,
            "completed": key in joined_done,
        }
        if row["joined"]:
            row["joinLabel"] = "অংশগ্রহণরত"
        elif row["completed"]:
            row["joinLabel"] = "সম্পন্ন"
        elif not row["canJoin"] and o.get("isLocationEvent"):
            row["joinLabel"] = "পূর্ণ"
        else:
            row["joinLabel"] = "অংশ নিন"
        out.append(row)
    return out


def ensure_activity_from_task_id(user, pk, defaults=None):
    """
    Resolve task id (VA-1 | ASG-2 | INC-3) to a VolunteerActivity, creating if needed.
    Returns (activity, error_response).
    """
    defaults = defaults or {}
    raw = str(pk)

    if raw.upper().startswith("VA-"):
        try:
            act_id = int(raw.split("-", 1)[1])
        except ValueError:
            return None, Response({"detail": "Invalid task id"}, status=400)
        act = VolunteerActivity.objects.filter(pk=act_id, user=user).first()
        if not act:
            return None, Response({"detail": "Activity not found"}, status=404)
        return act, None

    assignment_id = None
    incident_id = None
    if raw.upper().startswith("ASG-"):
        try:
            assignment_id = int(raw.split("-", 1)[1])
        except ValueError:
            return None, Response({"detail": "Invalid task id"}, status=400)
    elif raw.upper().startswith("INC-"):
        try:
            incident_id = int(raw.split("-", 1)[1])
        except ValueError:
            return None, Response({"detail": "Invalid task id"}, status=400)
    else:
        try:
            n = int(raw)
        except ValueError:
            return None, Response({"detail": "Invalid task id"}, status=400)
        if ResponseAssignment.objects.filter(pk=n).exists():
            assignment_id = n
        else:
            incident_id = n

    # Existing activity?
    q = VolunteerActivity.objects.filter(user=user)
    if assignment_id:
        act = q.filter(assignment_id=assignment_id).first()
        if act:
            return act, None
        try:
            asg = ResponseAssignment.objects.select_related("incident", "incident__category").get(pk=assignment_id)
        except ResponseAssignment.DoesNotExist:
            return None, Response({"detail": "Task not found"}, status=404)
        inc = asg.incident
        title = (
            inc.title_bn or inc.title
            or (inc.category.name_bn if inc.category_id else f"সহায়তা #{inc.id}")
        )
        act = VolunteerActivity.objects.create(
            user=user,
            title=title,
            place=place_of(inc),
            detail=(inc.description_bn or inc.description or "")[:500],
            kind=defaults.get("kind", VolunteerActivity.Kind.ASSISTANCE),
            status=defaults.get("status", VolunteerActivity.Status.ONGOING),
            incident_id=inc.id,
            assignment_id=asg.id,
            people_helped=defaults.get("people_helped", 0),
            note=defaults.get("note", ""),
        )
        return act, None

    # Incident
    incidents, *_ = scoped_incidents(user)
    try:
        inc = incidents.get(pk=incident_id)
    except IncidentReport.DoesNotExist:
        return None, Response({"detail": "Task not found in your area"}, status=404)

    act = q.filter(incident_id=inc.id, operation_key="").first()
    if act:
        return act, None

    title = (
        inc.title_bn or inc.title
        or (inc.category.name_bn if inc.category_id else f"সহায়তা #{inc.id}")
    )
    act = VolunteerActivity.objects.create(
        user=user,
        title=title,
        place=place_of(inc),
        detail=(inc.description_bn or inc.description or "")[:500],
        kind=defaults.get("kind", VolunteerActivity.Kind.ASSISTANCE),
        status=defaults.get("status", VolunteerActivity.Status.ONGOING),
        incident_id=inc.id,
        people_helped=defaults.get("people_helped", 0),
        note=defaults.get("note", ""),
    )
    return act, None


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
        helped = (
            VolunteerActivity.objects.filter(user=user).aggregate(s=Sum("people_helped"))["s"]
            or 0
        )
        # Prefer logged help; fall back to area estimate
        people_display = helped if helped else people

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
                "label": "সহায়তাপ্রাপ্ত / প্রয়োজন",
                "value": people_display,
                "hint": "আপনার লগ ও এলাকার অনুমান",
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

def collect_evidence_urls(incident, request=None):
    """Evidence from EvidenceAttachment.file_url (Supabase public links)."""
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
        items.append({
            "url": url,
            "kind": kind,
            "name": name or str(url).rsplit("/", 1)[-1],
        })

    try:
        from incidents.models import EvidenceAttachment
        for ev in EvidenceAttachment.objects.filter(incident=incident).order_by("id"):
            url = getattr(ev, "file_url", None) or getattr(ev, "file_path", None)
            kind = getattr(ev, "file_type", None) or "file"
            name = getattr(ev, "original_file_name", None) or getattr(ev, "file_name", None)
            add(url, kind=kind, name=name)
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
                add(url, kind=kind, name=getattr(obj, "original_file_name", None) or getattr(obj, "name", None))
        except Exception:
            continue
    return items


def serialize_report_detail(r, request=None):
    """Safe detail payload — never raises on missing optional fields."""
    try:
        base = serialize_report(r)
    except Exception:
        cat = getattr(r, "category", None)
        base = {
            "id": r.id,
            "type": "flood",
            "title": getattr(r, "title_bn", None) or getattr(r, "title", None) or f"রিপোর্ট #{r.id}",
            "description": getattr(r, "description_bn", None) or getattr(r, "description", None) or "",
            "district": getattr(r, "district", None) or "",
            "upazila": getattr(r, "upazila", None) or "",
            "place": getattr(r, "village", None) or getattr(r, "address", None) or "",
            "severity": "MODERATE",
            "status": "PENDING",
            "incident_time": getattr(r, "incident_time", None),
            "time": getattr(r, "incident_time", None) or getattr(r, "created_at", None),
            "affected": getattr(r, "affected_people_estimate", None),
            "category": {"id": getattr(r, "category_id", None)} if getattr(r, "category_id", None) else {},
            "reporter": None,
        }

    reporter_phone = None
    try:
        if r.reporter_id and not getattr(r, "is_anonymous", False):
            u = r.reporter
            reporter_phone = getattr(u, "phone", None) or getattr(u, "mobile", None)
            if not base.get("reporter"):
                name = getattr(u, "full_name", None) or getattr(u, "username", None)
                if name:
                    base["reporter"] = {"name": name}
    except Exception:
        pass

    lat = getattr(r, "latitude", None) or getattr(r, "lat", None)
    lng = getattr(r, "longitude", None) or getattr(r, "lng", None) or getattr(r, "lon", None)
    status_raw = (getattr(r, "status", None) or "").lower()

    evidence = []
    try:
        evidence = collect_evidence_urls(r, request=request)
    except Exception:
        evidence = []

    base.update({
        "address": getattr(r, "address", None) or "",
        "village": getattr(r, "village", None) or "",
        "union": getattr(r, "union", None) or "",
        "isSos": bool(getattr(r, "is_sos", False)),
        "isAnonymous": bool(getattr(r, "is_anonymous", False)),
        "situation": getattr(r, "situation", None) or "",
        "latitude": lat,
        "longitude": lng,
        "createdAt": getattr(r, "created_at", None),
        "updatedAt": getattr(r, "updated_at", None),
        "reporterPhone": reporter_phone,
        "affectedFamilies": getattr(r, "affected_families_estimate", None),
        "evidence": evidence,
        "canVerify": status_raw in ("submitted", "pending", "under_review"),
    })
    return base


class VolunteerReportsView(APIView):
    permission_classes = PERMS

    def get(self, request):
        incidents, *_ = scoped_incidents(request.user)
        rows = [serialize_report(r) for r in incidents.order_by("-created_at")[:200]]
        return Response(rows)


class VolunteerReportDetailView(APIView):
    """
    GET volunteer/reports/<pk>/
    Full incident detail + evidence (Supabase file_url) for volunteer review before verify.
    """
    permission_classes = PERMS

    def get(self, request, pk):
        incident = None
        # 1) Prefer area-scoped report
        try:
            incidents, *_ = scoped_incidents(request.user)
            incident = incidents.select_related("category", "reporter").filter(pk=pk).first()
        except Exception:
            incident = None

        # 2) Fallback: any report by id (so detail never 404 if list showed it)
        if incident is None:
            try:
                incident = (
                    IncidentReport.objects
                    .select_related("category", "reporter")
                    .filter(pk=pk)
                    .first()
                )
            except Exception:
                incident = None

        if incident is None:
            return Response(
                {"detail": f"রিপোর্ট #{pk} পাওয়া যায়নি"},
                status=404,
            )

        try:
            payload = serialize_report_detail(incident, request=request)
            return Response(payload)
        except Exception as exc:
            # Last-resort minimal payload so modal still opens
            return Response({
                "id": incident.id,
                "title": getattr(incident, "title", None) or f"রিপোর্ট #{pk}",
                "description": getattr(incident, "description", None) or "",
                "district": getattr(incident, "district", None) or "",
                "upazila": getattr(incident, "upazila", None) or "",
                "status": "PENDING",
                "evidence": [],
                "canVerify": True,
                "detail_error": str(exc),
            })


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
        people = (
            VolunteerActivity.objects.filter(user=user).aggregate(s=Sum("people_helped"))["s"]
            or 0
        )
        # Timeline from VolunteerActivity
        acts = []
        for a in VolunteerActivity.objects.filter(user=user).order_by("-updated_at")[:12]:
            acts.append({
                "id": f"va-{a.id}",
                "kind": "mission" if a.kind in ("RESCUE", "RELIEF") else "report",
                "title": a.title,
                "place": a.place or "",
                "body": a.note or a.detail or "",
                "time": a.updated_at,
            })
        if not acts:
            acts = build_activities(user, limit=12)
        return Response({
            "stats": [
                {"label": "সম্পন্ন কার্যক্রম", "value": done, "tone": "emerald", "icon": "CircleCheck"},
                {"label": "নির্ধারিত আছে", "value": open_t, "tone": "amber", "icon": "ClipboardList"},
                {"label": "সহায়তাপ্রাপ্ত মানুষ", "value": people, "tone": "lagoon", "icon": "HandHeart"},
            ],
            "activities": acts,
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
            "rescue-operations": self.rescue_operations,
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
        pending_qs = incidents.filter(status__in=PENDING_STATUSES).order_by("-created_at")
        pending = pending_qs.count()
        high = incidents.filter(priority__in=["high", "critical"]).exclude(
            status__in=["resolved", "closed", "rejected"]
        ).count()
        rows = [serialize_report(r) for r in incidents.order_by("-created_at")[:100]]
        pending_rows = [serialize_report(r) for r in pending_qs[:50]]
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
                    "type": "verificationTable",
                    "title": "লোকেশন ও রিপোর্ট যাচাই সারি",
                    "subtitle": "যাচাই করলে এলাকায় উদ্ধার অভিযান তৈরি হবে এবং স্থানীয় স্বেচ্ছাসেবকরা নোটিফিকেশন পাবেন",
                    "items": pending_rows,
                },
                {
                    "type": "reportTable",
                    "title": f"কমিউনিটি রিপোর্ট ({region})",
                    "items": rows,
                },
            ],
        }

    def assistance(self, user):
        tasks = build_tasks(user, limit=50)
        open_t = sum(1 for t in tasks if t["status"] != "DONE")
        ongoing = sum(1 for t in tasks if t["status"] == "ONGOING")
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        done_month = VolunteerActivity.objects.filter(
            user=user, status="DONE", updated_at__gte=month_start
        ).count()
        people = (
            VolunteerActivity.objects.filter(user=user).aggregate(s=Sum("people_helped"))["s"]
            or 0
        )
        return {
            "stats": [
                {"label": "নির্ধারিত কার্যক্রম", "value": open_t, "tone": "lagoon", "icon": "ListChecks"},
                {"label": "চলমান", "value": ongoing, "tone": "amber", "icon": "Activity"},
                {"label": "এ মাসে সম্পন্ন", "value": done_month, "tone": "emerald", "icon": "CircleCheck"},
                {"label": "সহায়তাপ্রাপ্ত", "value": people, "tone": "sky", "icon": "HandHeart"},
            ],
            "blocks": [
                {
                    "type": "taskCards",
                    "title": "সহায়তা ও ত্রাণ কার্যক্রম",
                    "subtitle": "স্ট্যাটাস, নোট ও সহায়তাপ্রাপ্ত মানুষ আপডেট করুন",
                    "items": tasks,
                    "editable": True,
                },
            ],
        }

    def rescue_operations(self, user):
        ops = build_operations_for_volunteer(user)
        running = [o for o in ops if o.get("status") == "IN_PROGRESS"]
        joined = sum(1 for o in ops if o.get("joined"))
        rescued = sum(o.get("rescued") or 0 for o in ops)
        return {
            "stats": [
                {"label": "চলমান অভিযান", "value": len(running), "tone": "red", "icon": "LifeBuoy"},
                {"label": "আমার অংশগ্রহণ", "value": joined, "tone": "sky", "icon": "Users"},
                {"label": "উদ্ধারকৃত (এলাকা)", "value": rescued, "tone": "emerald", "icon": "HandHeart"},
            ],
            "blocks": [
                {
                    "type": "volunteerOps",
                    "title": "উদ্ধার ও ত্রাণ অভিযান",
                    "subtitle": "এলাকার চলমান অভিযানে অংশ নিন",
                    "items": ops,
                },
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
# TASK COMPLETE / UPDATE  (points 3 & 5)
# ============================================================

class VolunteerCompleteTaskView(APIView):
    """Mark assistance/relief activity DONE. Body: note?, people_helped?"""
    permission_classes = PERMS

    def post(self, request, pk):
        user = request.user
        note = (request.data.get("note") or "").strip()
        people = request.data.get("people_helped")
        try:
            people = int(people) if people is not None and people != "" else None
        except (TypeError, ValueError):
            people = None

        defaults = {"status": VolunteerActivity.Status.DONE}
        if note:
            defaults["note"] = note
        if people is not None:
            defaults["people_helped"] = max(0, people)

        act, err = ensure_activity_from_task_id(user, pk, defaults={
            "status": VolunteerActivity.Status.DONE,
            "note": note,
            "people_helped": people or 0,
        })
        if err:
            return err

        act.status = VolunteerActivity.Status.DONE
        if note:
            act.note = note
        if people is not None:
            act.people_helped = max(0, people)
        act.due_label = "সম্পন্ন"
        act.save()

        # Mirror onto ResponseAssignment when linked
        if act.assignment_id:
            try:
                asg = ResponseAssignment.objects.get(pk=act.assignment_id)
                asg.status = "completed"
                try:
                    asg.save(update_fields=["status", "updated_at"])
                except Exception:
                    asg.save(update_fields=["status"])
                ResponseAction.objects.create(
                    assignment=asg,
                    action_type="assistance",
                    notes=f"volunteer:{user.id}:done|{act.note}",
                    personnel_count=max(1, act.people_helped or 1),
                )
            except ResponseAssignment.DoesNotExist:
                pass
        elif act.incident_id:
            asg = (
                ResponseAssignment.objects
                .filter(incident_id=act.incident_id)
                .exclude(status__in=["declined", "cancelled"])
                .order_by("-created_at")
                .first()
            )
            if asg:
                ResponseAction.objects.create(
                    assignment=asg,
                    action_type="assistance",
                    notes=f"volunteer:{user.id}:done|{act.note}",
                    personnel_count=max(1, act.people_helped or 1),
                )

        return Response(act.to_task_dict())


class VolunteerUpdateTaskView(APIView):
    """
    Update volunteer activity — status, note, people_helped, detail.
    Point 3 + 5: help logging & activity updates.
    """
    permission_classes = PERMS

    def post(self, request, pk):
        user = request.user
        status = (request.data.get("status") or "").upper()
        note = request.data.get("note")
        detail = request.data.get("detail")
        people = request.data.get("people_helped")

        try:
            people = int(people) if people is not None and people != "" else None
        except (TypeError, ValueError):
            return Response({"detail": "people_helped must be a number"}, status=400)

        allowed = {"PENDING", "ONGOING", "DONE"}
        if status and status not in allowed:
            return Response({"detail": "Invalid status"}, status=400)

        start_status = status if status in allowed else VolunteerActivity.Status.ONGOING
        act, err = ensure_activity_from_task_id(user, pk, defaults={
            "status": start_status,
            "note": (note or "").strip() if note is not None else "",
            "people_helped": people if people is not None else 0,
        })
        if err:
            return err

        if status in allowed:
            act.status = status
            if status == "DONE":
                act.due_label = "সম্পন্ন"
            elif status == "ONGOING":
                act.due_label = "চলমান"
        if note is not None:
            act.note = str(note).strip()
        if detail is not None:
            act.detail = str(detail).strip()[:500]
        if people is not None:
            act.people_helped = max(0, people)
        act.save()

        if act.status == "DONE" and act.assignment_id:
            try:
                asg = ResponseAssignment.objects.get(pk=act.assignment_id)
                asg.status = "completed"
                try:
                    asg.save(update_fields=["status", "updated_at"])
                except Exception:
                    asg.save(update_fields=["status"])
            except ResponseAssignment.DoesNotExist:
                pass

        return Response(act.to_task_dict())


# ============================================================
# RESCUE / RELIEF JOIN  (point 4)
# ============================================================

class VolunteerOperationsView(APIView):
    permission_classes = PERMS

    def get(self, request):
        return Response(build_operations_for_volunteer(request.user))


class VolunteerJoinOperationView(APIView):
    """
    Join an area rescue/relief operation.
    key = operation id e.g. OP-12
    body: { kind?: "RELIEF"|"RESCUE", note? }
    """
    permission_classes = PERMS

    def post(self, request, key):
        user = request.user
        op_key = str(key)
        kind = (request.data.get("kind") or "RELIEF").upper()
        if kind not in ("RELIEF", "RESCUE", "ASSISTANCE"):
            kind = "RELIEF"
        note = (request.data.get("note") or "").strip()

        # Already joined & active?
        existing = VolunteerActivity.objects.filter(
            user=user, operation_key=op_key
        ).exclude(status="DONE").first()
        if existing:
            return Response(existing.to_task_dict())

        # Find operation from area list
        ops = build_operations_for_volunteer(user)
        op = next((o for o in ops if str(o.get("id")) == op_key), None)
        if not op:
            return Response({"detail": "Operation not found in your area"}, status=404)

        # Location event capacity check
        if op_key.upper().startswith("EV-"):
            try:
                from dashboard.models import RescueEvent
                eid = int(op_key.split("-", 1)[1])
                ev = RescueEvent.objects.filter(pk=eid).first()
                if not ev:
                    return Response({"detail": "ইভেন্ট পাওয়া যায়নি"}, status=404)
                if ev.status != RescueEvent.Status.OPEN:
                    return Response({"detail": "ইভেন্ট বন্ধ"}, status=400)
                if ev.joined_total() >= ev.max_volunteers:
                    return Response(
                        {"detail": f"সর্বোচ্চ {ev.max_volunteers} জন স্বেচ্ছাসেবক — আর জায়গা নেই"},
                        status=400,
                    )
                if kind not in ("RELIEF", "RESCUE"):
                    kind = ev.mission_type
            except Exception as exc:
                return Response({"detail": str(exc)}, status=400)

        # Extract incident id from OP-{id}
        incident_id = None
        if op_key.upper().startswith("OP-"):
            try:
                incident_id = int(op_key.split("-", 1)[1])
            except ValueError:
                incident_id = None

        act = VolunteerActivity.objects.create(
            user=user,
            title=op.get("title") or f"অভিযান {op_key}",
            place=op.get("district") or "",
            detail=f"নেতৃত্বে: {op.get('lead') or '—'} • দল: {op.get('teams') or 0}",
            note=note,
            kind=kind,
            status=VolunteerActivity.Status.ONGOING,
            operation_key=op_key,
            incident_id=incident_id,
            due_label="চলমান",
            people_helped=0,
        )
        return Response(act.to_task_dict(), status=201)



class VolunteerLeaveOperationView(APIView):
    """
    POST volunteer/operations/<key>/leave/
    Volunteer leaves a joined operation/event.
    """
    permission_classes = PERMS

    def post(self, request, key):
        user = request.user
        op_key = str(key)
        acts = VolunteerActivity.objects.filter(user=user, operation_key=op_key)
        if not acts.exists():
            return Response({"detail": "আপনি এই ইভেন্টে যুক্ত নন"}, status=404)
        deleted, _ = acts.delete()
        return Response({"detail": "ইভেন্ট থেকে বেরিয়ে এসেছেন", "id": op_key, "removed": deleted})


# ============================================================
# ACTIVITY HISTORY  (point 5)
# ============================================================

class VolunteerActivitiesView(APIView):
    permission_classes = PERMS

    def get(self, request):
        user = request.user
        qs = VolunteerActivity.objects.filter(user=user)
        status = (request.query_params.get("status") or "").upper()
        kind = (request.query_params.get("kind") or "").upper()
        if status in ("PENDING", "ONGOING", "DONE"):
            qs = qs.filter(status=status)
        if kind in ("ASSISTANCE", "RELIEF", "RESCUE", "OTHER"):
            qs = qs.filter(kind=kind)
        rows = [a.to_task_dict() for a in qs.order_by("-updated_at")[:100]]
        people = qs.aggregate(s=Sum("people_helped"))["s"] or 0
        return Response({
            "items": rows,
            "stats": {
                "total": len(rows),
                "done": sum(1 for r in rows if r["status"] == "DONE"),
                "ongoing": sum(1 for r in rows if r["status"] == "ONGOING"),
                "peopleHelped": people,
            },
        })



# ============================================================
# VERIFY REPORT + CREATE RESCUE OPERATION + NOTIFY
# ============================================================

def area_volunteers(district, upazila=None, exclude_user=None):
    """
    Volunteers in the same district (zilla). Upazila is optional soft filter —
    primary match is district so all district volunteers get the operation invite.
    """
    roles = ["COMMUNITY_VOLUNTEER", "VOLUNTEER"]
    qs = User.objects.filter(role__in=roles)
    if exclude_user is not None:
        qs = qs.exclude(pk=exclude_user.pk)

    if not district:
        return list(qs[:80])

    # User.district text field
    by_user = list(qs.filter(district__icontains=district)[:80])
    found_ids = {u.pk for u in by_user}

    # CommunityVolunteerProfile.district if present
    try:
        from users.models import CommunityVolunteerProfile
        profile_qs = CommunityVolunteerProfile.objects.filter(
            user__role__in=roles,
            district__icontains=district,
        ).select_related("user")
        if exclude_user is not None:
            profile_qs = profile_qs.exclude(user_id=exclude_user.pk)
        for p in profile_qs[:80]:
            if p.user_id not in found_ids:
                by_user.append(p.user)
                found_ids.add(p.user_id)
    except Exception:
        pass

    return by_user[:80]


def create_operation_for_incident(incident, leader_user):
    """
    Ensure a ResponseAssignment exists for this incident (acts as rescue op seed).
    Returns (operation_key, assignment_or_None).
    """
    op_key = f"OP-{incident.id}"
    asg = (
        ResponseAssignment.objects
        .filter(incident=incident)
        .exclude(status__in=["declined", "cancelled"])
        .order_by("-created_at")
        .first()
    )
    if not asg:
        try:
            asg = ResponseAssignment.objects.create(
                incident=incident,
                status="pending",
            )
        except Exception:
            # Schema may require assigned_to — still return logical op key
            asg = None

    # Leader's own activity as operation participation
    VolunteerActivity.objects.get_or_create(
        user=leader_user,
        operation_key=op_key,
        defaults={
            "title": incident.title_bn or incident.title or f"উদ্ধার অভিযান #{incident.id}",
            "place": place_of(incident),
            "detail": (incident.description_bn or incident.description or "")[:500],
            "kind": VolunteerActivity.Kind.RESCUE,
            "status": VolunteerActivity.Status.ONGOING,
            "incident_id": incident.id,
            "assignment_id": asg.id if asg else None,
            "due_label": "চলমান",
        },
    )
    return op_key, asg


class VolunteerVerifyReportView(APIView):
    """
    Volunteer verifies a local report only — does NOT create rescue operations.
    Officer announces events from verified reports; volunteers may then attend/join.

    POST body: { "action": "VERIFY" | "REJECT" }
    """
    permission_classes = PERMS

    def post(self, request, pk):
        user = request.user
        action = (request.data.get("action") or "").upper()

        incidents, *_ = scoped_incidents(user)
        try:
            incident = incidents.get(pk=pk)
        except IncidentReport.DoesNotExist:
            # fallback: allow by id if scoped miss
            try:
                incident = IncidentReport.objects.get(pk=pk)
            except IncidentReport.DoesNotExist:
                return Response(
                    {"detail": "রিপোর্ট আপনার এলাকায় নেই বা পাওয়া যায়নি"},
                    status=404,
                )

        if action == "VERIFY":
            incident.status = "verified"
            try:
                incident.save(update_fields=["status", "updated_at"])
            except Exception:
                incident.save(update_fields=["status"])

            try:
                VerificationRecord.objects.create(
                    incident=incident,
                    verifier=user,
                    status="verified",
                    priority_assigned=getattr(incident, "priority", None),
                    severity_assigned=getattr(incident, "severity", None),
                )
            except Exception:
                try:
                    VerificationRecord.objects.create(
                        incident=incident,
                        verifier=user,
                        status="verified",
                    )
                except Exception:
                    pass

            return Response({
                "id": incident.id,
                "action": "VERIFY",
                "status": "VERIFIED",
                "operation": None,
                "notified": 0,
                "message": "যাচাই সম্পন্ন। অফিসার ইভেন্ট ঘোষণা করলে আপনি অংশ নিতে পারবেন।",
            })

        if action == "REJECT":
            incident.status = "rejected"
            try:
                incident.save(update_fields=["status", "updated_at"])
            except Exception:
                incident.save(update_fields=["status"])
            try:
                VerificationRecord.objects.create(
                    incident=incident,
                    verifier=user,
                    status="rejected",
                )
            except Exception:
                pass
            return Response({"id": incident.id, "action": "REJECT", "status": "REJECTED"})

        return Response({"detail": "Invalid action"}, status=400)