from django.db import models


class QuizPack(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name
