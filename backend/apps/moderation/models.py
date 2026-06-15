from django.db import models


class ReviewAction(models.Model):
    target_type = models.CharField(max_length=100)
    target_id = models.PositiveBigIntegerField()
    action = models.CharField(max_length=50)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.action} {self.target_type}:{self.target_id}"
