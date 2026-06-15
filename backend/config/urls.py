from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI

from apps.core.api import router as core_router

api = NinjaAPI(title="Guess Song API")
api.add_router("", core_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
