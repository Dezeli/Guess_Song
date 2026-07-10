import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0005_remove_artistseed_ingestion_a_status_8ef043_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="YoutubeArtistDiscoveryCursor",
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
                ("name", models.CharField(default="default", max_length=100, unique=True)),
                (
                    "source_type",
                    models.CharField(
                        choices=[("b", "Public chart sample")],
                        default="b",
                        max_length=30,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("paused", "Paused"),
                            ("completed", "Completed"),
                        ],
                        default="active",
                        max_length=30,
                    ),
                ),
                ("last_artist_name", models.CharField(blank=True, max_length=255)),
                ("last_artist_key", models.CharField(blank=True, max_length=255)),
                ("processed_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
                ("params", models.JSONField(blank=True, default=dict)),
                ("last_run_started_at", models.DateTimeField(blank=True, null=True)),
                ("last_run_finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "last_artist_seed",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="ingestion.artistseed",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="youtubeartistdiscoverycursor",
            index=models.Index(
                fields=["status", "source_type"],
                name="ingestion_y_status_972529_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="youtubeartistdiscoverycursor",
            index=models.Index(
                fields=["last_run_started_at"],
                name="ingestion_y_last_ru_7ca4a9_idx",
            ),
        ),
    ]
