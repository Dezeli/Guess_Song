from django.contrib import admin

from .models import AnswerSubmission, GameRound, GameSession, Participant, Room, RoundSkipVote


class ParticipantInline(admin.TabularInline):
    model = Participant
    extra = 0
    readonly_fields = ["joined_at", "last_seen_at", "left_at"]


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ["code", "status", "created_at", "expires_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["code", "host_token"]
    readonly_fields = ["created_at"]
    inlines = [ParticipantInline]


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ["nickname", "room", "score", "is_host", "status", "joined_at", "left_at"]
    list_filter = ["is_host", "status", "joined_at"]
    search_fields = ["nickname", "room__code", "session_token"]
    autocomplete_fields = ["room"]


class GameRoundInline(admin.TabularInline):
    model = GameRound
    extra = 0
    autocomplete_fields = ["question"]


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = [
        "room",
        "quiz_pack",
        "status",
        "current_round_index",
        "started_at",
        "finished_at",
    ]
    list_filter = ["status", "started_at"]
    search_fields = ["room__code", "quiz_pack__name"]
    autocomplete_fields = ["room", "quiz_pack"]
    inlines = [GameRoundInline]


@admin.register(GameRound)
class GameRoundAdmin(admin.ModelAdmin):
    list_display = ["session", "question", "round_index", "started_at", "ended_at"]
    list_filter = ["started_at", "ended_at"]
    search_fields = ["session__room__code", "question__answer_title", "question__answer_artist"]
    autocomplete_fields = ["session", "question"]


@admin.register(AnswerSubmission)
class AnswerSubmissionAdmin(admin.ModelAdmin):
    list_display = [
        "round",
        "participant",
        "answer_raw",
        "is_correct",
        "score_awarded",
        "response_time_ms",
        "submitted_at",
    ]
    list_filter = ["is_correct", "submitted_at"]
    search_fields = ["answer_raw", "normalized_answer", "participant__nickname"]
    autocomplete_fields = ["round", "participant"]


@admin.register(RoundSkipVote)
class RoundSkipVoteAdmin(admin.ModelAdmin):
    list_display = ["round", "participant", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["round__session__room__code", "participant__nickname"]
    autocomplete_fields = ["round", "participant"]
