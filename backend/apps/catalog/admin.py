from django.contrib import admin

from .models import (
    Album,
    Artist,
    Chart,
    ChartEntry,
    Track,
    TrackArtist,
    TrackExternalId,
    YouTubeCandidate,
)


@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ["name", "artist_type", "country"]
    list_filter = ["artist_type", "country"]
    search_fields = ["name", "normalized_name"]


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ["title", "artist", "release_date"]
    list_filter = ["release_date"]
    search_fields = ["title", "normalized_title", "artist__name"]


class TrackArtistInline(admin.TabularInline):
    model = TrackArtist
    extra = 0


class TrackExternalIdInline(admin.TabularInline):
    model = TrackExternalId
    extra = 0


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ["title", "primary_artist", "release_date", "duration_ms", "isrc"]
    list_filter = ["release_date"]
    search_fields = ["title", "normalized_title", "primary_artist__name", "isrc"]
    inlines = [TrackArtistInline, TrackExternalIdInline]


@admin.register(Chart)
class ChartAdmin(admin.ModelAdmin):
    list_display = ["source", "chart_type", "year", "week", "name"]
    list_filter = ["source", "chart_type", "year", "week"]
    search_fields = ["name"]


@admin.register(ChartEntry)
class ChartEntryAdmin(admin.ModelAdmin):
    list_display = ["chart", "rank", "title_raw", "artist_raw", "track"]
    list_filter = ["chart__source", "chart__chart_type", "chart__year"]
    search_fields = ["title_raw", "artist_raw", "track__title", "track__primary_artist__name"]
    autocomplete_fields = ["track"]


@admin.register(YouTubeCandidate)
class YouTubeCandidateAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "track",
        "channel_title",
        "duration_seconds",
        "official_score",
        "review_status",
    ]
    list_filter = ["review_status", "official_score"]
    search_fields = ["title", "video_id", "channel_title", "track__title"]
    autocomplete_fields = ["track"]
