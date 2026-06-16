from django.contrib import admin

from .models import QualityReport, ReviewAction


@admin.register(ReviewAction)
class ReviewActionAdmin(admin.ModelAdmin):
    list_display = ["target_type", "target_id", "action", "created_by", "created_at"]
    list_filter = ["action", "target_type", "created_at"]
    search_fields = ["target_type", "target_id", "reason"]
    readonly_fields = ["created_at"]


@admin.register(QualityReport)
class QualityReportAdmin(admin.ModelAdmin):
    list_display = ["target_type", "reason", "song", "youtube_source", "created_at"]
    list_filter = ["target_type", "reason"]
    search_fields = [
        "song__title",
        "song__primary_artist__name",
        "youtube_source__title",
        "youtube_source__video_id",
        "message",
    ]
    autocomplete_fields = ["song", "youtube_source"]
