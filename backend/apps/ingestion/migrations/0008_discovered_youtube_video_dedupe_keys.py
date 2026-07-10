from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0007_discoveredyoutubevideo"),
    ]

    operations = [
        migrations.AddField(
            model_name="discoveredyoutubevideo",
            name="artist_title_key",
            field=models.CharField(blank=True, db_index=True, max_length=600),
        ),
        migrations.AddField(
            model_name="discoveredyoutubevideo",
            name="normalized_artist_name",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name="discoveredyoutubevideo",
            name="normalized_song_title",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddIndex(
            model_name="discoveredyoutubevideo",
            index=models.Index(
                fields=["artist_title_key", "status"],
                name="ingestion_d_artist__462ad9_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="discoveredyoutubevideo",
            constraint=models.UniqueConstraint(
                condition=models.Q(("artist_title_key__gt", "")),
                fields=("artist_title_key",),
                name="unique_discovered_youtube_artist_title_key",
            ),
        ),
    ]
