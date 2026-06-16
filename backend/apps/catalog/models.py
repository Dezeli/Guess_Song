from django.db import models


class Artist(models.Model):
    class ArtistType(models.TextChoices):
        SOLO = "solo", "Solo"
        GROUP = "group", "Group"
        UNKNOWN = "unknown", "Unknown"

    name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255, db_index=True)
    artist_type = models.CharField(
        max_length=20,
        choices=ArtistType.choices,
        default=ArtistType.UNKNOWN,
    )
    country = models.CharField(max_length=2, blank=True)

    def __str__(self) -> str:
        return self.name


class Album(models.Model):
    title = models.CharField(max_length=255)
    normalized_title = models.CharField(max_length=255, db_index=True)
    artist = models.ForeignKey(Artist, on_delete=models.PROTECT, related_name="albums")
    release_date = models.DateField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.title


class Song(models.Model):
    class MetadataProvider(models.TextChoices):
        SPOTIFY = "spotify", "Spotify"
        APPLE_MUSIC = "apple_music", "Apple Music"
        MUSICBRAINZ = "musicbrainz", "MusicBrainz"
        YOUTUBE_MUSIC = "youtube_music", "YouTube Music"
        MELON = "melon", "Melon"
        GENIE = "genie", "Genie"
        BUGS = "bugs", "Bugs"
        CIRCLE = "circle", "Circle"
        MANUAL = "manual", "Manual"

    title = models.CharField(max_length=255)
    normalized_title = models.CharField(max_length=255, db_index=True)
    primary_artist = models.ForeignKey(Artist, on_delete=models.PROTECT, related_name="songs")
    album = models.ForeignKey(
        Album,
        on_delete=models.SET_NULL,
        related_name="songs",
        null=True,
        blank=True,
    )
    release_date = models.DateField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    isrc = models.CharField(max_length=20, blank=True, db_index=True)
    release_year = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    canonical_provider = models.CharField(
        max_length=30,
        choices=MetadataProvider.choices,
        blank=True,
    )
    canonical_provider_track_id = models.CharField(max_length=255, blank=True, db_index=True)
    metadata_confidence = models.PositiveSmallIntegerField(default=0)
    approved = models.BooleanField(default=False, db_index=True)
    playable = models.BooleanField(default=False, db_index=True)
    report_count = models.PositiveIntegerField(default=0)
    blocked = models.BooleanField(default=False, db_index=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["canonical_provider", "canonical_provider_track_id"],
                condition=(
                    models.Q(canonical_provider__gt="")
                    & models.Q(canonical_provider_track_id__gt="")
                ),
                name="unique_song_canonical_provider_track_id",
            ),
            models.UniqueConstraint(
                fields=["isrc"],
                condition=models.Q(isrc__gt=""),
                name="unique_song_isrc",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} - {self.primary_artist}"


class SongArtist(models.Model):
    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary"
        FEATURED = "featured", "Featured"
        COMPOSER = "composer", "Composer"
        LYRICIST = "lyricist", "Lyricist"
        PRODUCER = "producer", "Producer"

    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name="artist_links")
    artist = models.ForeignKey(Artist, on_delete=models.PROTECT, related_name="song_links")
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.PRIMARY)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["song", "order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["song", "artist", "role"],
                name="unique_song_artist_role",
            )
        ]

    def __str__(self) -> str:
        return f"{self.song} / {self.artist} ({self.role})"


class Chart(models.Model):
    class Source(models.TextChoices):
        CIRCLE = "circle", "Circle"

    class ChartType(models.TextChoices):
        DIGITAL_YEARLY = "digital_yearly", "Digital yearly"
        DIGITAL_MONTHLY = "digital_monthly", "Digital monthly"
        DIGITAL_WEEKLY = "digital_weekly", "Digital weekly"
        SINGING_ROOM_WEEKLY = "singing_room_weekly", "Singing room weekly"
        DOWNLOAD_WEEKLY = "download_weekly", "Download weekly"
        BGM_WEEKLY = "bgm_weekly", "BGM weekly"
        V_COLORING_WEEKLY = "v_coloring_weekly", "V coloring weekly"
        BELL_WEEKLY = "bell_weekly", "Bell weekly"
        RING_WEEKLY = "ring_weekly", "Ring weekly"
        STREAMING_WEEKLY = "streaming_weekly", "Streaming weekly"
        GLOBAL_KPOP_WEEKLY = "global_kpop_weekly", "Global K-pop weekly"

    source = models.CharField(max_length=30, choices=Source.choices)
    chart_type = models.CharField(max_length=50, choices=ChartType.choices)
    year = models.PositiveSmallIntegerField(db_index=True)
    week = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    name = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "chart_type", "year"],
                condition=models.Q(week__isnull=True),
                name="unique_chart_source_type_year_no_week",
            ),
            models.UniqueConstraint(
                fields=["source", "chart_type", "year", "week"],
                condition=models.Q(week__isnull=False),
                name="unique_chart_source_type_year_week",
            ),
        ]

    def __str__(self) -> str:
        base = self.name or f"{self.source} {self.chart_type} {self.year}"
        if self.week is not None:
            return f"{base} W{self.week}"
        return base


class ChartEntry(models.Model):
    chart = models.ForeignKey(Chart, on_delete=models.CASCADE, related_name="entries")
    rank = models.PositiveSmallIntegerField()
    title_raw = models.CharField(max_length=255)
    artist_raw = models.CharField(max_length=255)
    song = models.ForeignKey(
        Song,
        on_delete=models.SET_NULL,
        related_name="chart_entries",
        null=True,
        blank=True,
    )
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["chart", "rank"]
        constraints = [
            models.UniqueConstraint(fields=["chart", "rank"], name="unique_chart_entry_rank")
        ]

    def __str__(self) -> str:
        return f"{self.chart} #{self.rank} {self.title_raw}"


class SongExternalId(models.Model):
    class Provider(models.TextChoices):
        SPOTIFY = "spotify", "Spotify"
        MUSICBRAINZ = "musicbrainz", "MusicBrainz"
        YOUTUBE = "youtube", "YouTube"
        CIRCLE = "circle", "Circle"

    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name="external_ids")
    provider = models.CharField(max_length=30, choices=Provider.choices)
    external_id = models.CharField(max_length=255)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "external_id"],
                name="unique_song_external_provider_id",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.external_id}"


class YoutubeSource(models.Model):
    class SourceType(models.TextChoices):
        OFFICIAL_MV = "official_mv", "Official MV"
        OFFICIAL_AUDIO = "official_audio", "Official Audio"
        TOPIC_ART_TRACK = "topic_art_track", "Topic / Art Track"
        LABEL_CHANNEL = "label_channel", "Label / Distributor Channel"
        ARTIST_CHANNEL = "artist_channel", "Artist Official Channel"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        AUTO_APPROVED = "auto_approved", "Auto approved"
        NEEDS_REVIEW = "needs_review", "Needs review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        BLOCKED = "blocked", "Blocked"
        UNAVAILABLE = "unavailable", "Unavailable"

    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name="youtube_sources")
    video_id = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=500)
    channel_title = models.CharField(max_length=255)
    channel_id = models.CharField(max_length=255, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    view_count = models.PositiveBigIntegerField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    source_type = models.CharField(
        max_length=30,
        choices=SourceType.choices,
        default=SourceType.OFFICIAL_MV,
    )
    priority = models.PositiveSmallIntegerField(default=100)
    official_score = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
    )
    report_count = models.PositiveIntegerField(default=0)
    reject_reason = models.TextField(blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "-official_score", "-view_count", "id"]

    def __str__(self) -> str:
        return f"{self.title} ({self.video_id})"
