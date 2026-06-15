from django.db import models


class Room(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        PLAYING = "playing", "Playing"
        FINISHED = "finished", "Finished"
        CLOSED = "closed", "Closed"

    code = models.CharField(max_length=12, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING)
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.code
