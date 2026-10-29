import uuid
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse


ROAST_LEVEL_CHOICES = (
    ("light", "Light"),
    ("medium_light", "Medium-Light"),
    ("medium", "Medium"),
    ("medium_dark", "Medium-Dark"),
    ("dark", "Dark"),
)


class BeanInfo(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    origin = models.CharField(max_length=120, blank=True)
    process = models.CharField(max_length=80, blank=True, help_text="e.g., Washed, Natural, Honey")
    cultivar = models.CharField(max_length=120, blank=True, help_text="e.g., Bourbon, Caturra, Heirloom")
    roast_recommendation = models.CharField(max_length=80, blank=True, help_text="e.g., City+ to Full City")
    flavor_keywords = models.CharField(max_length=255, blank=True, help_text="Brief manual notes (e.g., Citrus, Chocolate, Floral)")
    sweetmarias_url = models.URLField(blank=True, help_text="Link to the Sweet Maria's product page")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Bean Info"
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.origin})"


class Roast(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    alog_uuid = models.CharField(max_length=64, unique=True, db_index=True)
    
    # NEW: Link to the bean library
    bean_info = models.ForeignKey(BeanInfo, on_delete=models.SET_NULL, null=True, blank=True, related_name="roasts")

    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="uploaded_roasts",
    )
    owner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="owned_roasts",
        help_text="User who claimed this roast. Only owner/admin may edit.",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    title = models.CharField(max_length=255, blank=True)
    beans = models.CharField(max_length=255, blank=True, db_index=True)
    origin = models.CharField(max_length=120, blank=True, db_index=True)
    roast_level = models.CharField(
        max_length=40, blank=True, db_index=True, choices=ROAST_LEVEL_CHOICES,
    )
    roast_date = models.DateField(null=True, db_index=True)
    roast_time = models.TimeField(null=True)
    batch_nr = models.IntegerField(null=True)
    operator = models.CharField(max_length=120, blank=True, db_index=True)
    organization = models.CharField(max_length=120, blank=True)
    roaster_type = models.CharField(max_length=120, blank=True)
    ambient_temp = models.FloatField(null=True)

    weight_in_g = models.FloatField(null=True)
    weight_out_g = models.FloatField(null=True)
    weight_loss_pct = models.FloatField(null=True)

    timex = models.JSONField(default=list)
    temp_bt = models.JSONField(default=list)
    temp_et = models.JSONField(default=list)
    extra_curves = models.JSONField(default=dict)
    computed = models.JSONField(default=dict)
    flavors = models.JSONField(default=list)
    flavor_labels = models.JSONField(default=list)
    raw = models.JSONField(default=dict)

    notes = models.TextField(blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    is_public = models.BooleanField(
        default=False,
        help_text="Private by default. Toggle to allow anonymous viewing.",
    )

    class Meta:
        ordering = ("-roast_date", "-roast_time")
        indexes = (
            models.Index(fields=["beans", "roast_date"]),
            models.Index(fields=["origin", "roast_level"]),
        )

    def __str__(self):
        return f"{self.beans or 'Roast'} - {self.roast_date}"

    def get_absolute_url(self):
        return reverse("roast_detail", kwargs={"uuid": self.uuid})

    @property
    def duration_s(self):
        return self.timex[-1] if self.timex else 0

    # --- permission helpers ---
    def can_view(self, user):
        if self.is_public:
            return True
        if user and user.is_authenticated:
            return True
        return False

    def can_edit(self, user):
        if not user or not user.is_authenticated:
            return False
        return user == self.owner or user.is_staff

    def can_delete(self, user):
        return self.can_edit(user)

    def can_claim(self, user):
        if not user or not user.is_authenticated:
            return False
        return self.owner is None or self.owner.is_superuser


class RoastEvent(models.Model):
    EVENT_CHOICES = (
        ("CHARGE", "Charge"),
        ("TP", "Turning Point"),
        ("DRY", "Dry End"),
        ("FC", "First Crack"),
        ("FCs", "First Crack Start"),
        ("SC", "Second Crack"),
        ("DROP", "Drop"),
        ("COOL", "Cool"),
        ("NOTE", "Note"),
    )
    roast = models.ForeignKey(Roast, related_name="events", on_delete=models.CASCADE)
    event_type = models.CharField(max_length=16, choices=EVENT_CHOICES)
    time_s = models.FloatField()
    bt = models.FloatField(null=True)
    et = models.FloatField(null=True)
    label = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("time_s",)

    def __str__(self):
        return f"{self.event_type} @ {self.time_s:.1f}s"


class RoastComment(models.Model):
    RECOMMEND_CHOICES = (
        (True, "Recommend"),
        (False, "Do not recommend"),
    )
    
    roast = models.ForeignKey(Roast, related_name="comments", on_delete=models.CASCADE)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    body = models.TextField(max_length=4000)
    parent = models.ForeignKey(
        "self", null=True, blank=True,
        related_name="replies", on_delete=models.CASCADE,
    )
    recommends = models.BooleanField(null=True, blank=True, choices=RECOMMEND_CHOICES)

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.author.username}: {self.body[:40]}"