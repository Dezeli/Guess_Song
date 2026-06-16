import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_song_pipeline_models"),
        ("moderation", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="QualityReport",
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
                    "target_type",
                    models.CharField(
                        choices=[
                            ("song", "Song"),
                            ("youtube_source", "YouTube source"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("wrong_title", "Wrong title"),
                            ("wrong_artist", "Wrong artist"),
                            ("wrong_audio", "Wrong audio"),
                            ("unavailable", "Unavailable"),
                            ("unofficial_video", "Unofficial video"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=50,
                    ),
                ),
                ("message", models.TextField(blank=True)),
                ("reporter_fingerprint", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "song",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quality_reports",
                        to="catalog.song",
                    ),
                ),
                (
                    "youtube_source",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quality_reports",
                        to="catalog.youtubesource",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["target_type", "created_at"],
                        name="moderation__target__83e940_idx",
                    )
                ],
            },
        ),
    ]
