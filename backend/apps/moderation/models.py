from django.db import models


class ReviewAction(models.Model):
    class Action(models.TextChoices):
        APPROVE = "approve", "Approve"
        REJECT = "reject", "Reject"
        REQUEST_REVIEW = "request_review", "Request review"
        DISABLE = "disable", "Disable"

    target_type = models.CharField(max_length=100)
    target_id = models.PositiveBigIntegerField()
    action = models.CharField(max_length=50, choices=Action.choices)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        related_name="review_actions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.action} {self.target_type}:{self.target_id}"
