from django.contrib import admin

from .models import (
    Album,
    Artist,
    Chart,
    ChartEntry,
    Song,
    SongArtist,
    SongExternalId,
    YoutubeSource,
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


class SongArtistInline(admin.TabularInline):
    model = SongArtist
    extra = 0


class SongExternalIdInline(admin.TabularInline):
    model = SongExternalId
    extra = 0


@admin.register(Song)
class SongAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "primary_artist",
        "release_date",
        "duration_ms",
        "isrc",
        "approved",
        "playable",
        "blocked",
    ]
    list_filter = ["approved", "playable", "blocked", "release_date", "canonical_provider"]
    search_fields = ["title", "normalized_title", "primary_artist__name", "isrc"]
    inlines = [SongArtistInline, SongExternalIdInline]


@admin.register(Chart)
class ChartAdmin(admin.ModelAdmin):
    list_display = ["source", "chart_type", "year", "week", "name"]
    list_filter = ["source", "chart_type", "year", "week"]
    search_fields = ["name"]


@admin.register(ChartEntry)
class ChartEntryAdmin(admin.ModelAdmin):
    list_display = ["chart", "rank", "title_raw", "artist_raw", "song"]
    list_filter = ["chart__source", "chart__chart_type", "chart__year"]
    search_fields = ["title_raw", "artist_raw", "song__title", "song__primary_artist__name"]
    autocomplete_fields = ["song"]


@admin.register(YoutubeSource)
class YoutubeSourceAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "song",
        "channel_title",
        "source_type",
        "duration_seconds",
        "official_score",
        "status",
    ]
    list_filter = ["status", "source_type", "official_score"]
    search_fields = ["title", "video_id", "channel_title", "song__title"]
    autocomplete_fields = ["song"]
