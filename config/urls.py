from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import admin_login_redirect
from apps.common.views import healthz, robots_txt

admin.site.site_header = "Boshqaruv"
admin.site.site_title = "Boshqaruv"
# Admin o'zining (rate limitsiz) login formasini ishlatmaydi.
admin.site.login = admin_login_redirect

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("robots.txt", robots_txt),
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.people.urls")),
    path("", include("apps.contracts.urls")),
    path("", include("apps.finance.urls")),
    path("", include("apps.dorm.urls")),
    path("", include("apps.academics.urls")),
    path("payroll/", include("apps.payroll.urls")),
    path("director/", include("apps.director.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
