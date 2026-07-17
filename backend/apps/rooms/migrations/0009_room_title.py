from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rooms", "0008_gamesession_first_round_starts_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="room",
            name="title",
            field=models.CharField(default="한소절 방", max_length=40),
        ),
    ]
