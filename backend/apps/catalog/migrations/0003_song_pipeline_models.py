import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_remove_chart_unique_chart_source_type_year_and_more"),
        ("quizzes", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Track",
            new_name="Song",
        ),
        migrations.RenameModel(
            old_name="TrackArtist",
            new_name="SongArtist",
        ),
        migrations.RenameModel(
            old_name="TrackExternalId",
            new_name="SongExternalId",
        ),
        migrations.RenameModel(
            old_name="YouTubeCandidate",
            new_name="YoutubeSource",
        ),
        migrations.RemoveConstraint(
            model_name="songartist",
            name="unique_track_artist_role",
        ),
        migrations.RemoveConstraint(
            model_name="songexternalid",
            name="unique_track_external_provider_id",
        ),
        migrations.RenameField(
            model_name="chartentry",
            old_name="track",
            new_name="song",
        ),
        migrations.RenameField(
            model_name="songartist",
            old_name="track",
            new_name="song",
        ),
        migrations.RenameField(
            model_name="songexternalid",
            old_name="track",
            new_name="song",
        ),
        migrations.RenameField(
            model_name="youtubesource",
            old_name="track",
            new_name="song",
        ),
        migrations.RenameField(
            model_name="youtubesource",
            old_name="review_status",
            new_name="status",
        ),
        migrations.AddField(
            model_name="song",
            name="approved",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="song",
            name="blocked",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="song",
            name="canonical_provider",
            field=models.CharField(
                blank=True,
                choices=[
                    ("spotify", "Spotify"),
                    ("apple_music", "Apple Music"),
                    ("musicbrainz", "MusicBrainz"),
                    ("youtube_music", "YouTube Music"),
                    ("melon", "Melon"),
                    ("genie", "Genie"),
                    ("bugs", "Bugs"),
                    ("circle", "Circle"),
                    ("manual", "Manual"),
                ],
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="song",
            name="canonical_provider_track_id",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name="song",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="song",
            name="metadata_confidence",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="song",
            name="playable",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="song",
            name="release_year",
            field=models.PositiveSmallIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="song",
            name="report_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="song",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="youtubesource",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="youtubesource",
            name="last_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="youtubesource",
            name="priority",
            field=models.PositiveSmallIntegerField(default=100),
        ),
        migrations.AddField(
            model_name="youtubesource",
            name="report_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="youtubesource",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("official_mv", "Official MV"),
                    ("official_audio", "Official Audio"),
                    ("topic_art_track", "Topic / Art Track"),
                    ("label_channel", "Label / Distributor Channel"),
                    ("artist_channel", "Artist Official Channel"),
                ],
                default="official_mv",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="youtubesource",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="album",
            name="artist",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="albums",
                to="catalog.artist",
            ),
        ),
        migrations.AlterField(
            model_name="album",
            name="release_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="chartentry",
            name="song",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="chart_entries",
                to="catalog.song",
            ),
        ),
        migrations.AlterField(
            model_name="song",
            name="album",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="songs",
                to="catalog.album",
            ),
        ),
        migrations.AlterField(
            model_name="song",
            name="primary_artist",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="songs",
                to="catalog.artist",
            ),
        ),
        migrations.AlterField(
            model_name="songartist",
            name="artist",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="song_links",
                to="catalog.artist",
            ),
        ),
        migrations.AlterField(
            model_name="songartist",
            name="song",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="artist_links",
                to="catalog.song",
            ),
        ),
        migrations.AlterField(
            model_name="songexternalid",
            name="song",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="external_ids",
                to="catalog.song",
            ),
        ),
        migrations.AlterField(
            model_name="youtubesource",
            name="song",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="youtube_sources",
                to="catalog.song",
            ),
        ),
        migrations.AlterField(
            model_name="youtubesource",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("auto_approved", "Auto approved"),
                    ("needs_review", "Needs review"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("blocked", "Blocked"),
                    ("unavailable", "Unavailable"),
                ],
                default="pending",
                max_length=30,
            ),
        ),
        migrations.AlterModelOptions(
            name="songartist",
            options={"ordering": ["song", "order", "id"]},
        ),
        migrations.AlterModelOptions(
            name="youtubesource",
            options={"ordering": ["priority", "-official_score", "-view_count", "id"]},
        ),
        migrations.AddConstraint(
            model_name="song",
            constraint=models.UniqueConstraint(
                condition=models.Q(("canonical_provider__gt", ""))
                & models.Q(("canonical_provider_track_id__gt", "")),
                fields=("canonical_provider", "canonical_provider_track_id"),
                name="unique_song_canonical_provider_track_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="song",
            constraint=models.UniqueConstraint(
                condition=models.Q(("isrc__gt", "")),
                fields=("isrc",),
                name="unique_song_isrc",
            ),
        ),
        migrations.AddConstraint(
            model_name="songartist",
            constraint=models.UniqueConstraint(
                fields=("song", "artist", "role"),
                name="unique_song_artist_role",
            ),
        ),
        migrations.AddConstraint(
            model_name="songexternalid",
            constraint=models.UniqueConstraint(
                fields=("provider", "external_id"),
                name="unique_song_external_provider_id",
            ),
        ),
    ]
