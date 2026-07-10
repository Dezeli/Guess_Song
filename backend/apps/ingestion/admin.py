from django.contrib import admin

from .models import (
    ArtistSeed,
    DiscoveredYoutubeVideo,
    IngestionJob,
    IngestionLog,
    RawCandidate,
    YoutubeArtistDiscoveryCursor,
)


class IngestionLogInline(admin.TabularInline):
    model = IngestionLog
    extra = 0
    readonly_fields = ["level", "message", "context", "created_at"]


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


@admin.register(RawCandidate)
class RawCandidateAdmin(admin.ModelAdmin):
    list_display = [
        "raw_title",
        "raw_artist",
        "source_type",
        "first_observed_year",
        "first_observed_month",
        "first_observed_sample_day",
        "status",
        "metadata_confidence",
        "matched_song",
    ]
    list_filter = ["source_type", "status", "enriched_provider", "first_observed_year"]
    search_fields = [
        "raw_title",
        "raw_artist",
        "raw_title_key",
        "raw_artist_key",
        "enriched_title",
        "enriched_artist",
        "enriched_isrc",
        "matched_song__title",
    ]
    autocomplete_fields = ["job", "matched_song"]


@admin.register(ArtistSeed)
class ArtistSeedAdmin(admin.ModelAdmin):
    list_display = [
        "display_artist",
        "source_type",
        "observed_count",
        "observed_sample_count",
        "observed_weight_score",
        "first_observed_year",
        "first_observed_month",
        "last_observed_year",
        "last_observed_month",
        "status",
        "youtube_search_attempt_count",
    ]
    list_filter = ["source_type", "status", "first_observed_year", "last_observed_year"]
    search_fields = ["raw_artist", "raw_artist_key", "display_artist"]
    autocomplete_fields = ["job"]


@admin.register(YoutubeArtistDiscoveryCursor)
class YoutubeArtistDiscoveryCursorAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "source_type",
        "status",
        "last_artist_name",
        "processed_count",
        "failed_count",
        "last_run_started_at",
        "last_run_finished_at",
    ]
    list_filter = ["source_type", "status", "last_run_started_at"]
    search_fields = ["name", "last_artist_name", "last_artist_key"]
    autocomplete_fields = ["last_artist_seed"]


@admin.register(DiscoveredYoutubeVideo)
class DiscoveredYoutubeVideoAdmin(admin.ModelAdmin):
    list_display = [
        "song_title",
        "artist_name",
        "uploaded_year",
        "uploaded_month",
        "official_score",
        "status",
        "youtube_url",
    ]
    list_filter = ["status", "uploaded_year", "uploaded_month", "official_score"]
    search_fields = [
        "song_title",
        "artist_name",
        "youtube_title",
        "video_id",
        "channel_title",
    ]
    autocomplete_fields = ["artist_seed", "job"]
    readonly_fields = ["created_at", "updated_at"]
