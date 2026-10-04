
import secrets

from django.db import models
from django.conf import settings


class Food(models.Model):
    # user=None means a shared food that everyone can see
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    serving_unit = models.CharField(max_length=50, default='1 serving')
    calories = models.FloatField()
    protein = models.FloatField(default=0)
    carbs = models.FloatField(default=0)
    fat = models.FloatField(default=0)

    def __str__(self):
        return f"{self.name} ({self.serving_unit})"


class Meal(models.Model):
    MEAL_TYPES = [
        ('breakfast', 'Breakfast'),
        ('lunch', 'Lunch'),
        ('dinner', 'Dinner'),
        ('snack', 'Snack'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True)
    food = models.ForeignKey(Food, on_delete=models.SET_NULL, null=True, blank=True)
    servings = models.FloatField(default=1)
    meal_type = models.CharField(max_length=10, choices=MEAL_TYPES, default='snack')
    name = models.CharField(max_length=100)
    calories = models.PositiveIntegerField()
    protein = models.FloatField(default=0)
    carbs = models.FloatField(default=0)
    fat = models.FloatField(default=0)
    eaten_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Activity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True)
    date = models.DateField()
    steps = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.date} - {self.steps} steps"


class Goal(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    calories = models.PositiveIntegerField(default=2000)
    protein = models.PositiveIntegerField(default=100)

    def __str__(self):
        return f"{self.user} goal"


class Badge(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code = models.CharField(max_length=30)
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'code'], name='unique_user_badge'),
        ]

    def __str__(self):
        return f"{self.user} - {self.code}"


class Challenge(models.Model):
    METRICS = [
        ('steps', 'Steps'),
        ('protein', 'Protein (g)'),
        ('logging', 'Days logged'),
    ]

    name = models.CharField(max_length=60)
    metric = models.CharField(max_length=10, choices=METRICS)
    start_date = models.DateField()
    end_date = models.DateField()
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_challenges'
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='challenges', blank=True
    )
    invite_code = models.CharField(max_length=20, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.invite_code:
            self.invite_code = secrets.token_urlsafe(8)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ReportPref(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    weekly_email = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user} weekly report: {self.weekly_email}"