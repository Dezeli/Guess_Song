import re
import unicodedata

from django.db import migrations, models


def normalize_raw_key(value):
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def populate_raw_keys(apps, schema_editor):
    RawCandidate = apps.get_model("ingestion", "RawCandidate")
    for candidate in RawCandidate.objects.all().iterator():
        candidate.raw_title_key = normalize_raw_key(candidate.raw_title)
        candidate.raw_artist_key = normalize_raw_key(candidate.raw_artist)
        if candidate.source_type != "b":
            candidate.source_type = "b"
        candidate.save(
            update_fields=[
                "source_type",
                "raw_title_key",
                "raw_artist_key",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0002_rawcandidate"),
    ]

    operations = [
        migrations.RenameField(
            model_name="rawcandidate",
            old_name="source",
            new_name="source_type",
        ),
        migrations.RemoveConstraint(
            model_name="rawcandidate",
            name="unique_raw_candidate_source_identifier",
        ),
        migrations.AddField(
            model_name="rawcandidate",
            name="first_observed_month",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="rawcandidate",
            name="first_observed_sample_day",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="rawcandidate",
            name="first_observed_year",
            field=models.PositiveSmallIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="rawcandidate",
            name="raw_artist_key",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name="rawcandidate",
            name="raw_title_key",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="rawcandidate",
            name="source_type",
            field=models.CharField(
                choices=[("b", "Public chart sample")],
                max_length=30,
            ),
        ),
        migrations.RunPython(populate_raw_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="rawcandidate",
            name="raw_artist_key",
            field=models.CharField(db_index=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="rawcandidate",
            name="raw_title_key",
            field=models.CharField(db_index=True, max_length=255),
        ),
        migrations.AddIndex(
            model_name="rawcandidate",
            index=models.Index(
                fields=["source_type", "raw_title_key", "raw_artist_key"],
                name="ingestion_r_source__191260_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="rawcandidate",
            constraint=models.UniqueConstraint(
                condition=models.Q(("source_identifier__gt", "")),
                fields=("source_type", "source_identifier"),
                name="unique_raw_candidate_source_identifier",
            ),
        ),
        migrations.AddConstraint(
            model_name="rawcandidate",
            constraint=models.UniqueConstraint(
                fields=("source_type", "raw_title_key", "raw_artist_key"),
                name="unique_raw_candidate_source_raw_keys",
            ),
        ),
    ]
