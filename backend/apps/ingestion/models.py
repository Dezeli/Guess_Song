from django.db import models


class IngestionJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    job_type = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    params = models.JSONField(default=dict, blank=True)
    total_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    fail_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.job_type} ({self.status})"


class IngestionLog(models.Model):
    class Level(models.TextChoices):
        DEBUG = "debug", "Debug"
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name="logs")
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    message = models.TextField()
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["job", "created_at", "id"]

    def __str__(self) -> str:
        return f"{self.level}: {self.message[:80]}"


class RawCandidate(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ENRICHED = "enriched", "Enriched"
        DUPLICATE = "duplicate", "Duplicate"
        REVIEW_REQUIRED = "review_required", "Review required"
        REJECTED = "rejected", "Rejected"
        PROMOTED = "promoted", "Promoted"

    class SourceType(models.TextChoices):
        B = "b", "Public chart sample"

    job = models.ForeignKey(
        IngestionJob,
        on_delete=models.SET_NULL,
        related_name="raw_candidates",
        null=True,
        blank=True,
    )
    source_type = models.CharField(max_length=30, choices=SourceType.choices)
    source_identifier = models.CharField(max_length=255, blank=True, db_index=True)
    raw_title = models.CharField(max_length=255)
    raw_artist = models.CharField(max_length=255)
    raw_title_key = models.CharField(max_length=255, db_index=True)
    raw_artist_key = models.CharField(max_length=255, db_index=True)
    raw_album = models.CharField(max_length=255, blank=True)
    raw_release_date = models.DateField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    first_observed_year = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    first_observed_month = models.PositiveSmallIntegerField(null=True, blank=True)
    first_observed_sample_day = models.PositiveSmallIntegerField(null=True, blank=True)

    enriched_provider = models.CharField(max_length=30, blank=True)
    enriched_provider_track_id = models.CharField(max_length=255, blank=True, db_index=True)
    enriched_title = models.CharField(max_length=255, blank=True)
    enriched_artist = models.CharField(max_length=255, blank=True)
    enriched_album = models.CharField(max_length=255, blank=True)
    enriched_release_date = models.DateField(null=True, blank=True)
    enriched_release_year = models.PositiveSmallIntegerField(null=True, blank=True)
    enriched_isrc = models.CharField(max_length=20, blank=True, db_index=True)
    enriched_duration_ms = models.PositiveIntegerField(null=True, blank=True)
    metadata_confidence = models.PositiveSmallIntegerField(default=0)
    metadata_payload = models.JSONField(default=dict, blank=True)

    matched_song = models.ForeignKey(
        "catalog.Song",
        on_delete=models.SET_NULL,
        related_name="raw_candidates",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    reject_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "metadata_confidence"]),
            models.Index(fields=["enriched_provider", "enriched_provider_track_id"]),
            models.Index(fields=["source_type", "raw_title_key", "raw_artist_key"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_type", "source_identifier"],
                condition=models.Q(source_identifier__gt=""),
                name="unique_raw_candidate_source_identifier",
            ),
            models.UniqueConstraint(
                fields=["source_type", "raw_title_key", "raw_artist_key"],
                name="unique_raw_candidate_source_raw_keys",
            ),
        ]

    def __str__(self) -> str:
        title = self.enriched_title or self.raw_title
        artist = self.enriched_artist or self.raw_artist
        return f"{title} - {artist} ({self.status})"


class ArtistSeed(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        YOUTUBE_SEARCHED = "youtube_searched", "YouTube searched"
        REVIEW_REQUIRED = "review_required", "Review required"
        REJECTED = "rejected", "Rejected"

    class SourceType(models.TextChoices):
        B = "b", "Public chart sample"

    job = models.ForeignKey(
        IngestionJob,
        on_delete=models.SET_NULL,
        related_name="artist_seeds",
        null=True,
        blank=True,
    )
    source_type = models.CharField(max_length=30, choices=SourceType.choices)
    raw_artist = models.CharField(max_length=255)
    raw_artist_key = models.CharField(max_length=255, db_index=True)
    display_artist = models.CharField(max_length=255)
    first_observed_year = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    first_observed_month = models.PositiveSmallIntegerField(null=True, blank=True)
    first_observed_sample_day = models.PositiveSmallIntegerField(null=True, blank=True)
    last_observed_year = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    last_observed_month = models.PositiveSmallIntegerField(null=True, blank=True)
    last_observed_sample_day = models.PositiveSmallIntegerField(null=True, blank=True)
    observed_count = models.PositiveIntegerField(default=0, db_index=True)
    observed_sample_count = models.PositiveIntegerField(default=0, db_index=True)
    observed_weight_score = models.PositiveIntegerField(default=0, db_index=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    youtube_search_attempt_count = models.PositiveIntegerField(default=0)
    last_youtube_search_attempt_at = models.DateTimeField(null=True, blank=True)
    metadata_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "-observed_weight_score", "-observed_count"]),
            models.Index(fields=["source_type", "raw_artist_key"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_type", "raw_artist_key"],
                name="unique_artist_seed_source_artist_key",
            )
        ]

    def __str__(self) -> str:
        return f"{self.display_artist} ({self.observed_count})"
