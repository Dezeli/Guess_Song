from django.db import models


class IngestionJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    job_type = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    params = models.JSONField(default=dict, blank=True)
    total_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    fail_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.job_type} ({self.status})"


class IngestionLog(models.Model):
    class Level(models.TextChoices):
        DEBUG = "debug", "Debug"
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name="logs")
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    message = models.TextField()
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["job", "created_at", "id"]

    def __str__(self) -> str:
        return f"{self.level}: {self.message[:80]}"
