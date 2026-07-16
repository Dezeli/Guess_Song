from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI

from apps.core.api import router as core_router
from apps.moderation.review_api import router as review_router
from apps.quizzes.api import router as quizzes_router
from apps.rooms.api import router as rooms_router

api = NinjaAPI(title="Guess Song API")
api.add_router("", core_router)
api.add_router("", quizzes_router)
api.add_router("", rooms_router)
api.add_router("", review_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
