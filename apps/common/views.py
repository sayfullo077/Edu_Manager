from django.http import HttpResponse, JsonResponse
from django.shortcuts import render


def csrf_failure(request, reason=""):
    """Sahifa uzoq ochiq qolib, CSRF token eskirganda tushunarli xabar."""
    return render(request, "errors/csrf.html", status=403)


def healthz(request):
    """Load balancer / Docker healthcheck uchun. Bazaga bormaydi — tez va arzon."""
    return JsonResponse({"status": "ok"})


def robots_txt(request):
    # Ichki boshqaruv tizimi — qidiruv tizimlari indekslamasin.
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
