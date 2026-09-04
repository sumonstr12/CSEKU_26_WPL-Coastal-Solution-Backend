from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static

api_urlpatterns = [
    path("",include("users.urls")),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/v1/", include(api_urlpatterns))
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

