from django.contrib import admin

from .models import IngestionJob, IngestionLog


class IngestionLogInline(admin.TabularInline):
    model = IngestionLog
    extra = 0
    readonly_fields = ["created_at"]


@admin.register(IngestionJob)
class IngestionJobAdmin(admin.ModelAdmin):
    list_display = [
        "job_type",
        "status",
        "total_count",
        "success_count",
        "fail_count",
        "started_at",
        "finished_at",
    ]
    list_filter = ["status", "job_type", "started_at"]
    search_fields = ["job_type", "error_message"]
    inlines = [IngestionLogInline]
