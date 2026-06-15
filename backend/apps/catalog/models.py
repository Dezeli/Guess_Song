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


class Track(models.Model):
    title = models.CharField(max_length=255)
    normalized_title = models.CharField(max_length=255, db_index=True)
    primary_artist = models.ForeignKey(Artist, on_delete=models.PROTECT, related_name="tracks")
    album = models.ForeignKey(
        Album,
        on_delete=models.SET_NULL,
        related_name="tracks",
        null=True,
        blank=True,
    )
    release_date = models.DateField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    isrc = models.CharField(max_length=20, blank=True, db_index=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"{self.title} - {self.primary_artist}"


class TrackArtist(models.Model):
    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary"
        FEATURED = "featured", "Featured"
        COMPOSER = "composer", "Composer"
        LYRICIST = "lyricist", "Lyricist"
        PRODUCER = "producer", "Producer"

    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="artist_links")
    artist = models.ForeignKey(Artist, on_delete=models.PROTECT, related_name="track_links")
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.PRIMARY)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["track", "order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["track", "artist", "role"],
                name="unique_track_artist_role",
            )
        ]

    def __str__(self) -> str:
        return f"{self.track} / {self.artist} ({self.role})"


class Chart(models.Model):
    class Source(models.TextChoices):
        CIRCLE = "circle", "Circle"

    class ChartType(models.TextChoices):
        DIGITAL_YEARLY = "digital_yearly", "Digital yearly"
        DIGITAL_MONTHLY = "digital_monthly", "Digital monthly"
        DIGITAL_WEEKLY = "digital_weekly", "Digital weekly"

    source = models.CharField(max_length=30, choices=Source.choices)
    chart_type = models.CharField(max_length=50, choices=ChartType.choices)
    year = models.PositiveSmallIntegerField(db_index=True)
    name = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "chart_type", "year"],
                name="unique_chart_source_type_year",
            )
        ]

    def __str__(self) -> str:
        return self.name or f"{self.source} {self.chart_type} {self.year}"


class ChartEntry(models.Model):
    chart = models.ForeignKey(Chart, on_delete=models.CASCADE, related_name="entries")
    rank = models.PositiveSmallIntegerField()
    title_raw = models.CharField(max_length=255)
    artist_raw = models.CharField(max_length=255)
    track = models.ForeignKey(
        Track,
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


class TrackExternalId(models.Model):
    class Provider(models.TextChoices):
        SPOTIFY = "spotify", "Spotify"
        MUSICBRAINZ = "musicbrainz", "MusicBrainz"
        YOUTUBE = "youtube", "YouTube"
        CIRCLE = "circle", "Circle"

    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="external_ids")
    provider = models.CharField(max_length=30, choices=Provider.choices)
    external_id = models.CharField(max_length=255)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "external_id"],
                name="unique_track_external_provider_id",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.external_id}"


class YouTubeCandidate(models.Model):
    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        AUTO_APPROVED = "auto_approved", "Auto approved"
        NEEDS_REVIEW = "needs_review", "Needs review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="youtube_candidates")
    video_id = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=500)
    channel_title = models.CharField(max_length=255)
    channel_id = models.CharField(max_length=255, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    view_count = models.PositiveBigIntegerField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    official_score = models.PositiveSmallIntegerField(default=0)
    review_status = models.CharField(
        max_length=30,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
    )
    reject_reason = models.TextField(blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-official_score", "-view_count", "id"]

    def __str__(self) -> str:
        return f"{self.title} ({self.video_id})"
