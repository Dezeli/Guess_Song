from django.contrib import admin

from .models import ReviewAction


@admin.register(ReviewAction)
class ReviewActionAdmin(admin.ModelAdmin):
    list_display = ["target_type", "target_id", "action", "created_by", "created_at"]
    list_filter = ["action", "target_type", "created_at"]
    search_fields = ["target_type", "target_id", "reason"]
    readonly_fields = ["created_at"]
