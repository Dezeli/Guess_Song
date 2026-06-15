from django.contrib import admin

from .models import QuizAnswerAlias, QuizPack, QuizPackQuestion, QuizQuestion


class QuizAnswerAliasInline(admin.TabularInline):
    model = QuizAnswerAlias
    extra = 0


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = [
        "answer_title",
        "answer_artist",
        "difficulty",
        "status",
        "start_time_seconds",
        "play_duration_seconds",
    ]
    list_filter = ["difficulty", "status", "prompt_type"]
    search_fields = ["answer_title", "answer_artist", "track__title", "track__primary_artist__name"]
    autocomplete_fields = ["track", "youtube_candidate", "source_chart_entry"]
    inlines = [QuizAnswerAliasInline]


class QuizPackQuestionInline(admin.TabularInline):
    model = QuizPackQuestion
    extra = 0
    autocomplete_fields = ["question"]


@admin.register(QuizPack)
class QuizPackAdmin(admin.ModelAdmin):
    list_display = ["name", "is_public"]
    list_filter = ["is_public"]
    search_fields = ["name", "description"]
    inlines = [QuizPackQuestionInline]
