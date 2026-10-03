"""O'qituvchi paneli sahifalari uchun umumiy kontekst (academics va payroll view'lari ishlatadi)."""

from . import selectors

PREVIEW_TEACHER_KEY = "preview_teacher"


def _preview_teacher(request):
    """Superadmin uchun: ?teacher=<pk> (sessiyada eslab qolinadi) — shu filial o'qituvchisi."""
    raw = request.GET.get("teacher")
    if raw is not None:
        request.session[PREVIEW_TEACHER_KEY] = raw
    raw = request.session.get(PREVIEW_TEACHER_KEY)
    if not raw or not str(raw).isdigit():
        return None
    return selectors.teacher_choices(request.branch).filter(pk=int(raw)).select_related("user").first()


def teacher_ctx(request, today) -> dict:
    """O'qituvchi (superadmin — «Superadmin ko'rinishi»da tanlangan) va tanlash ro'yxati."""
    ctx = {"today": today, "teacher": selectors.teacher_profile(request.user, request.branch)}
    if ctx["teacher"] is None and request.user.is_superuser and not request.impersonator:
        ctx["teacher"] = _preview_teacher(request)
        ctx["preview_teachers"] = selectors.teacher_choices(request.branch)
    return ctx
