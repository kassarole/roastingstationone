import json
import re
import pprint
import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Avg, Case, When, F, FloatField
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.template.loader import render_to_string

from .models import Roast, RoastComment
from .parser import parse_alog
from .forms import UploadForm, NoteForm, RoastMetaForm


# --- Session key for cross-page roast selection ---
SELECTION_SESSION_KEY = "compare_selected_uuids"
MAX_COMPARE = 6


def _get_selected_uuids(request):
    """Return the list of selected roast UUIDs stored in the session."""
    return list(request.session.get(SELECTION_SESSION_KEY, []))


def _save_selected_uuids(request, uuids):
    """Persist selected UUIDs (as strings, deduped, ordered) to session."""
    seen = set()
    cleaned = []
    for u in uuids:
        u = str(u)
        if u not in seen:
            seen.add(u)
            cleaned.append(u)
    request.session[SELECTION_SESSION_KEY] = cleaned[:MAX_COMPARE]
    request.session.modified = True


def _visible_roasts(user):
    """Queryset filtered by the caller's view permissions."""
    qs = Roast.objects.all()

    # Anonymous users only see public roasts
    if not user.is_authenticated:
        return qs.filter(is_public=True)

    # Any logged-in user (staff or regular) sees everything
    return qs


def home(request):
    return redirect("roast_list")


def roast_list(request):
    qs = _visible_roasts(request.user)

    # Annotate review stats
    qs = qs.annotate(
        total_reviews=Count("comments", filter=Q(comments__recommends__isnull=False)),
        positive_reviews=Count("comments", filter=Q(comments__recommends=True)),
    ).annotate(
        recommend_pct=Case(
            When(total_reviews=0, then=0),
            default=(F("positive_reviews") * 100) / F("total_reviews"),
            output_field=FloatField(),
        )
    )

    # --- Filters ---
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(beans__icontains=q)
            | Q(title__icontains=q)
            | Q(operator__icontains=q)
            | Q(origin__icontains=q)
            | Q(organization__icontains=q)
        )

    origin = request.GET.get("origin")
    if origin:
        qs = qs.filter(origin=origin)

    level = request.GET.get("level")
    if level:
        qs = qs.filter(roast_level=level)

    w_min = request.GET.get("w_min")
    if w_min:
        try:
            qs = qs.filter(weight_in_g__gte=float(w_min))
        except ValueError:
            pass

    w_max = request.GET.get("w_max")
    if w_max:
        try:
            qs = qs.filter(weight_in_g__lte=float(w_max))
        except ValueError:
            pass

    date_from = request.GET.get("from")
    if date_from:
        qs = qs.filter(roast_date__gte=date_from)
    date_to = request.GET.get("to")
    if date_to:
        qs = qs.filter(roast_date__lte=date_to)

    ror_min = request.GET.get("ror_min")
    if ror_min:
        try:
            qs = qs.filter(computed__total_ror__gte=float(ror_min))
        except (ValueError, Exception):
            pass

    # --- Sorting ---
    sort_by = request.GET.get("sort", "-roast_date")

    if sort_by == "reviews_high":
        qs = qs.order_by("-recommend_pct", "-total_reviews")
    elif sort_by == "reviews_low":
        qs = qs.filter(total_reviews__gt=0).order_by("recommend_pct", "-total_reviews")
    elif sort_by == "reviews_most":
        qs = qs.order_by("-total_reviews", "-recommend_pct")
    else:
        qs = qs.order_by("-roast_date", "-roast_time")

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))

    origins = (
        Roast.objects.exclude(origin="")
        .values_list("origin", flat=True)
        .distinct()
        .order_by("origin")
    )

    # --- Session-backed selection (persists across pages) ---
    selected_uuids = _get_selected_uuids(request)

    return render(request, "roasts/list.html", {
        "page": page,
        "origins": origins,
        "q": q,
        "selected_origin": origin or "",
        "selected_level": level or "",
        "w_min": w_min or "",
        "w_max": w_max or "",
        "date_from": date_from or "",
        "date_to": date_to or "",
        "ror_min": ror_min or "",
        "total": qs.count(),
        "current_sort": sort_by,
        # NEW: for cross-page checkbox state
        "selected_uuids": selected_uuids,
        "selected_count": len(selected_uuids),
        "max_compare": MAX_COMPARE,
    })


@require_POST
def toggle_selection(request, uuid):
    """Toggle a single roast UUID in the session-backed compare selection."""
    roast = get_object_or_404(Roast, uuid=uuid)
    if not roast.can_view(request.user):
        return JsonResponse({"error": "Not permitted"}, status=403)

    selected = _get_selected_uuids(request)
    uid = str(roast.uuid)

    if uid in selected:
        selected.remove(uid)
        is_selected = False
    else:
        if len(selected) >= MAX_COMPARE:
            return JsonResponse(
                {"error": f"You can compare at most {MAX_COMPARE} roasts.",
                 "selected": False,
                 "count": len(selected)},
                status=400,
            )
        selected.append(uid)
        is_selected = True

    _save_selected_uuids(request, selected)
    return JsonResponse({"selected": is_selected, "count": len(selected)})


@require_POST
def clear_selection(request):
    """Clear all compare selections."""
    request.session[SELECTION_SESSION_KEY] = []
    request.session.modified = True
    return JsonResponse({"count": 0})


@login_required
def upload(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            created, failed = [], []
            for f in form.cleaned_data["alog_files"]:
                try:
                    r = parse_alog(f, user=request.user)
                    created.append(r)
                except Exception as e:
                    failed.append((f.name, str(e)))
            for name, err in failed:
                messages.error(request, f"{name}: {err}")
            if created:
                messages.success(request, f"Imported {len(created)} roast(s) (private by default).")
            if len(created) == 1 and not failed:
                return redirect(created[0])
            return redirect("roast_list")
    else:
        form = UploadForm()
    return render(request, "roasts/upload.html", {"form": form})


def roast_detail(request, uuid):
    roast = get_object_or_404(Roast, uuid=uuid)
    if not roast.can_view(request.user):
        return redirect(f"/login/?next={request.path}")

    chart_payload = {
        "timex": roast.timex,
        "bt": roast.temp_bt,
        "et": roast.temp_et,
        "extra": roast.extra_curves,
        "events": [
            {"type": e.event_type, "time": e.time_s, "bt": e.bt, "et": e.et}
            for e in roast.events.all()
        ],
        "computed": roast.computed,
    }

    comments = roast.comments.select_related("author").filter(parent=None)

    # Review summary calculation
    reviews = roast.comments.exclude(recommends__isnull=True)
    total_reviews = reviews.count()
    positive_reviews = reviews.filter(recommends=True).count()
    recommend_pct = int((positive_reviews / total_reviews) * 100) if total_reviews > 0 else 0

    return render(request, "roasts/detail.html", {
        "roast": roast,
        "chart_payload_json": json.dumps(chart_payload),
        "comments": comments,
        "total_reviews": total_reviews,
        "positive_reviews": positive_reviews,
        "recommend_pct": recommend_pct,
        "note_form": NoteForm(),
        "meta_form": RoastMetaForm(instance=roast),
        "can_edit": roast.can_edit(request.user),
        "can_delete": roast.can_delete(request.user),
        "can_claim": roast.can_claim(request.user),
        # NEW: is this roast currently selected for compare?
        "in_compare": str(roast.uuid) in _get_selected_uuids(request),
    })


@login_required
@require_POST
def claim_ownership(request, uuid):
    roast = get_object_or_404(Roast, uuid=uuid)
    if not roast.can_claim(request.user):
        return HttpResponseBadRequest("Already claimed or not permitted.")
    roast.owner = request.user
    roast.save(update_fields=["owner"])
    messages.success(request, "You now own this roast. You can edit and delete it.")
    return redirect(roast)


@login_required
@require_POST
def delete_roast(request, uuid):
    roast = get_object_or_404(Roast, uuid=uuid)
    if not roast.can_delete(request.user):
        return HttpResponseBadRequest("Not permitted")
    roast.delete()
    messages.success(request, "Roast deleted.")
    return redirect("roast_list")


@login_required
@require_POST
def update_meta(request, uuid):
    roast = get_object_or_404(Roast, uuid=uuid)
    if not roast.can_edit(request.user):
        return HttpResponseBadRequest("Not permitted")
    form = RoastMetaForm(request.POST, instance=roast)
    if form.is_valid():
        form.save()
        messages.success(request, "Roast updated.")
    else:
        messages.error(request, "Invalid form data.")
    return redirect(roast)


@login_required
@require_POST
def add_comment(request, uuid):
    roast = get_object_or_404(Roast, uuid=uuid)
    if not roast.can_view(request.user):
        return JsonResponse({"error": "Not permitted"}, status=403)

    body = request.POST.get("body", "").strip()
    if not body:
        return JsonResponse({"error": "Empty comment"}, status=400)

    recommends_raw = request.POST.get("recommends")
    recommends = None
    if recommends_raw == "1":
        recommends = True
    elif recommends_raw == "0":
        recommends = False

    c = RoastComment.objects.create(
        roast=roast,
        author=request.user,
        body=body,
        recommends=recommends
    )

    html = render_to_string("roasts/_comment.html", {"comment": c, "user": request.user})

    return JsonResponse({
        "id": c.id,
        "html": html,
        "count": roast.comments.count(),
    })


@login_required
@require_POST
def delete_comment(request, uuid, pk):
    roast = get_object_or_404(Roast, uuid=uuid)
    c = get_object_or_404(RoastComment, pk=pk, roast=roast)
    if c.author != request.user and not request.user.is_staff:
        return HttpResponseBadRequest("Not permitted")
    c.delete()
    return JsonResponse({"ok": True})


@login_required
def compare(request):
    """Compare view: uses GET ?u=... if provided (shareable links),
    otherwise falls back to the session-backed selection."""
    uuids = request.GET.getlist("u")

    if not uuids:
        # Fall back to session selection for cross-page comparisons
        uuids = _get_selected_uuids(request)

    if not uuids:
        # Nothing to compare; send them back
        return redirect("roast_list")

    qs = _visible_roasts(request.user).filter(uuid__in=uuids)

    # Preserve the order of selection
    roast_dict = {str(r.uuid): r for r in qs}
    roasts = [roast_dict[u] for u in uuids if u in roast_dict][:MAX_COMPARE]

    payloads = []
    for r in roasts:
        payloads.append({
            "uuid": str(r.uuid),
            "label": f"{r.beans or 'Roast'} - {r.roast_date}",
            "timex": r.timex,
            "bt": r.temp_bt,
            "et": r.temp_et,
            "events": [
                {"type": e.event_type, "time": e.time_s, "bt": e.bt}
                for e in r.events.all()
            ],
        })

    return render(request, "roasts/compare.html", {
        "roasts": roasts,
        "payloads_json": json.dumps(payloads),
    })


@login_required
def stats(request):
    qs = _visible_roasts(request.user)

    # Top beans
    top_beans = (
        qs.exclude(beans="")
        .values("beans")
        .annotate(n=Count("id"))
        .order_by("-n")[:10]
    )

    # Top owners (group by owner username)
    top_owners = (
        qs.values("owner__username")
        .annotate(n=Count("id"))
        .order_by("-n")[:10]
    )

    avg_rating = qs.aggregate(avg=Avg("rating"))["avg"]

    return render(request, "roasts/stats.html", {
        "top_beans": top_beans,
        "top_owners": top_owners,
        "avg_rating": avg_rating,
        "total_roasts": qs.count(),
    })


@login_required
def download_alog(request, uuid):
    roast = get_object_or_404(Roast, uuid=uuid)
    if not roast.can_view(request.user):
        return HttpResponseBadRequest("Not permitted")

    # Make a copy so we don't accidentally save these changes to the database
    raw_data = dict(roast.raw)

    # Update the raw data with any edits made in the web app
    raw_data['title'] = roast.title
    raw_data['beans'] = roast.beans
    raw_data['roastertype'] = roast.roaster_type
    raw_data['operator'] = roast.operator
    raw_data['organization'] = roast.organization

    # Format it exactly like an Artisan .alog file (Python dict literal)
    alog_content = pprint.pformat(raw_data, indent=1, width=120)

    response = HttpResponse(alog_content, content_type="text/plain")

    filename = roast.beans or roast.title or "roast"
    filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)

    response['Content-Disposition'] = f'attachment; filename="{filename}.alog"'
    return response

# --- API views ---

import functools
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


def api_token_required(view_func):
    """
    Simple bearer-token auth for API endpoints.

    Reads token from the `Authorization: Bearer <token>` header (or
    `X-API-Token` for convenience). Compares against settings.API_TOKEN.

    If settings.API_TOKEN is unset, the endpoint is disabled.
    """
    @functools.wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        expected = getattr(settings, "API_TOKEN", None)
        if not expected:
            return JsonResponse({"error": "API disabled"}, status=503)

        auth = request.headers.get("Authorization", "")
        token = ""
        if auth.startswith("Bearer "):
            token = auth[len("Bearer "):].strip()
        if not token:
            token = request.headers.get("X-API-Token", "").strip()

        if not token or not secrets.compare_digest(token, expected):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        return view_func(request, *args, **kwargs)
    return _wrapped


def _serialize_roast(request, roast):
    """Compact JSON representation of a roast for API responses."""
    return {
        "uuid": str(roast.uuid),
        "title": roast.title,
        "beans": roast.beans,
        "origin": roast.origin,
        "roast_level": roast.roast_level,
        "operator": roast.operator,
        "organization": roast.organization,
        "roast_date": roast.roast_date.isoformat() if roast.roast_date else None,
        "roast_time": roast.roast_time.isoformat() if roast.roast_time else None,
        "weight_in_g": roast.weight_in_g,
        "weight_out_g": roast.weight_out_g,
        "is_public": roast.is_public,
        "owner": roast.owner.username if roast.owner_id else None,
        "computed": roast.computed,
        "url": request.build_absolute_uri(roast.get_absolute_url()) if hasattr(roast, "get_absolute_url") else None,
    }


@csrf_exempt
@require_http_methods(["POST"])
@api_token_required
def api_upload(request):
    """
    Upload one or more .alog files via multipart/form-data.

    Accepts files under either the `alog_files` field (matching UploadForm)
    or the `file` field (single-file convenience). Returns per-file results.

    Optional form field: `is_public` ("1"/"0") — defaults to False.
    Optional form field: `owner` (username) — only honored for staff tokens
    via a `?owner=` style override is not supported; instead pass
    `X-On-Behalf-Of: <username>` header and the token's user must be staff.
    """
    files = request.FILES.getlist("alog_files") or request.FILES.getlist("file")
    if not files:
        return JsonResponse({"error": "No files provided"}, status=400)

    is_public = request.POST.get("is_public", "0") in ("1", "true", "True", "yes")

    # Optional on-behalf-of for staff automation
    uploader = request.user if request.user.is_authenticated else None
    on_behalf = request.headers.get("X-On-Behalf-Of", "").strip()
    if on_behalf:
        if not (uploader and uploader.is_staff):
            return JsonResponse({"error": "X-On-Behalf-Of requires staff"}, status=403)
        from django.contrib.auth import get_user_model
        try:
            uploader = get_user_model().objects.get(username=on_behalf)
        except get_user_model().DoesNotExist:
            return JsonResponse({"error": f"Unknown user: {on_behalf}"}, status=400)

    created, failed = [], []
    for f in files:
        try:
            roast = parse_alog(f, user=uploader)
            if is_public:
                roast.is_public = True
                roast.save(update_fields=["is_public"])
            created.append(_serialize_roast(request, roast))
        except Exception as e:
            failed.append({"filename": f.name, "error": str(e)})

    status = 201 if created and not failed else (207 if created else 400)
    return JsonResponse(
        {"created": created, "failed": failed, "count": len(created)},
        status=status,
    )


@require_http_methods(["GET"])
@api_token_required
def api_roast_lookup(request, alog_uuid):
    """Look up a single roast by its Artisan alog UUID.

    Token auth is sufficient — visibility is not filtered, so private
    roasts are returned to any valid token holder.
    """
    roast = Roast.objects.filter(alog_uuid=alog_uuid).first()
    if roast is None:
        return JsonResponse({"error": "Not found"}, status=404)

    return JsonResponse(_serialize_roast(request, roast))