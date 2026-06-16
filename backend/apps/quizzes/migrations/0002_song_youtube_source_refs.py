import django.db.models.deletion
from django.db import migrations, models


def approve_existing_playable_songs(apps, schema_editor):
    QuizQuestion = apps.get_model("quizzes", "QuizQuestion")
    Song = apps.get_model("catalog", "Song")
    YoutubeSource = apps.get_model("catalog", "YoutubeSource")

    approved_questions = QuizQuestion.objects.filter(status="approved")
    song_ids = approved_questions.values_list("song_id", flat=True)
    source_ids = approved_questions.values_list("youtube_source_id", flat=True)
    Song.objects.filter(id__in=song_ids).update(approved=True, playable=True)
    YoutubeSource.objects.filter(id__in=source_ids).update(status="approved")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_song_pipeline_models"),
        ("quizzes", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="quizquestion",
            old_name="track",
            new_name="song",
        ),
        migrations.RenameField(
            model_name="quizquestion",
            old_name="youtube_candidate",
            new_name="youtube_source",
        ),
        migrations.AlterField(
            model_name="quizquestion",
            name="song",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="questions",
                to="catalog.song",
            ),
        ),
        migrations.AlterField(
            model_name="quizquestion",
            name="youtube_source",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="questions",
                to="catalog.youtubesource",
            ),
        ),
        migrations.RunPython(approve_existing_playable_songs, migrations.RunPython.noop),
    ]
