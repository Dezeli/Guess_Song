import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0006_youtubeartistdiscoverycursor"),
    ]

    operations = [
        migrations.CreateModel(
            name="DiscoveredYoutubeVideo",
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
                ("song_title", models.CharField(max_length=255)),
                ("artist_name", models.CharField(max_length=255)),
                ("youtube_url", models.URLField(max_length=255)),
                ("video_id", models.CharField(max_length=32, unique=True)),
                ("youtube_title", models.CharField(max_length=500)),
                ("channel_title", models.CharField(max_length=255)),
                ("channel_id", models.CharField(blank=True, max_length=255)),
                (
                    "uploaded_year",
                    models.PositiveSmallIntegerField(blank=True, db_index=True, null=True),
                ),
                (
                    "uploaded_month",
                    models.PositiveSmallIntegerField(blank=True, db_index=True, null=True),
                ),
                ("official_score", models.PositiveSmallIntegerField(db_index=True, default=0)),
                ("source_type", models.CharField(blank=True, max_length=30)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("discovered", "Discovered"),
                            ("review_required", "Review required"),
                            ("rejected", "Rejected"),
                            ("promoted", "Promoted"),
                        ],
                        default="discovered",
                        max_length=30,
                    ),
                ),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "artist_seed",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="discovered_youtube_videos",
                        to="ingestion.artistseed",
                    ),
                ),
                (
                    "job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="discovered_youtube_videos",
                        to="ingestion.ingestionjob",
                    ),
                ),
            ],
            options={
                "ordering": [
                    "artist_name",
                    "-official_score",
                    "-uploaded_year",
                    "-uploaded_month",
                    "id",
                ],
            },
        ),
        migrations.AddIndex(
            model_name="discoveredyoutubevideo",
            index=models.Index(
                fields=["status", "-official_score"],
                name="ingestion_d_status_f4ce74_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="discoveredyoutubevideo",
            index=models.Index(
                fields=["artist_name", "song_title"],
                name="ingestion_d_artist__e5afab_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="discoveredyoutubevideo",
            index=models.Index(
                fields=["uploaded_year", "uploaded_month"],
                name="ingestion_d_uploade_6cdd65_idx",
            ),
        ),
    ]
