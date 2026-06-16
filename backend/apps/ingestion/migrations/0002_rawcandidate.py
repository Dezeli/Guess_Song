import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_song_pipeline_models"),
        ("ingestion", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RawCandidate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("circle", "Circle"),
                            ("spotify", "Spotify"),
                            ("apple_music", "Apple Music"),
                            ("musicbrainz", "MusicBrainz"),
                            ("youtube", "YouTube"),
                            ("manual", "Manual"),
                            ("other", "Other"),
                        ],
                        max_length=30,
                    ),
                ),
                ("source_identifier", models.CharField(blank=True, db_index=True, max_length=255)),
                ("raw_title", models.CharField(max_length=255)),
                ("raw_artist", models.CharField(max_length=255)),
                ("raw_album", models.CharField(blank=True, max_length=255)),
                ("raw_release_date", models.DateField(blank=True, null=True)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("enriched_provider", models.CharField(blank=True, max_length=30)),
                (
                    "enriched_provider_track_id",
                    models.CharField(blank=True, db_index=True, max_length=255),
                ),
                ("enriched_title", models.CharField(blank=True, max_length=255)),
                ("enriched_artist", models.CharField(blank=True, max_length=255)),
                ("enriched_album", models.CharField(blank=True, max_length=255)),
                ("enriched_release_date", models.DateField(blank=True, null=True)),
                ("enriched_release_year", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("enriched_isrc", models.CharField(blank=True, db_index=True, max_length=20)),
                ("enriched_duration_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("metadata_confidence", models.PositiveSmallIntegerField(default=0)),
                ("metadata_payload", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("enriched", "Enriched"),
                            ("duplicate", "Duplicate"),
                            ("review_required", "Review required"),
                            ("rejected", "Rejected"),
                            ("promoted", "Promoted"),
                        ],
                        default="pending",
                        max_length=30,
                    ),
                ),
                ("reject_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="raw_candidates",
                        to="ingestion.ingestionjob",
                    ),
                ),
                (
                    "matched_song",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="raw_candidates",
                        to="catalog.song",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["status", "metadata_confidence"],
                        name="ingestion_r_status_f96548_idx",
                    ),
                    models.Index(
                        fields=["enriched_provider", "enriched_provider_track_id"],
                        name="ingestion_r_enriche_bf9dcc_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("source_identifier__gt", "")),
                        fields=("source", "source_identifier"),
                        name="unique_raw_candidate_source_identifier",
                    )
                ],
            },
        ),
    ]
