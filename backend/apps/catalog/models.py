from django.db import models


class Artist(models.Model):
    name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255, db_index=True)

    def __str__(self) -> str:
        return self.name
