import secrets

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q


class FoodQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Shared foods (no owner) plus the user's own custom foods."""
        return self.filter(Q(owner__isnull=True) | Q(owner=user))


class Food(models.Model):
    name = models.CharField(max_length=100)
    calories = models.FloatField(help_text="per 100g")
    protein = models.FloatField(help_text="grams per 100g")
    carbs = models.FloatField(help_text="grams per 100g")
    fat = models.FloatField(help_text="grams per 100g")
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='custom_foods',
                              help_text="Empty = shared with everyone")
    barcode = models.CharField(max_length=32, blank=True)
    image_url = models.URLField(max_length=500, blank=True, help_text="Optional photo (https)")
    category = models.CharField(max_length=10, blank=True, choices=[
        ('protein', 'Protein'), ('carbs', 'Carbs'), ('fats', 'Fats'), ('other', 'Other')],
        help_text="Leave empty to detect automatically")

    objects = FoodQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self.category:
            from .foodcategory import classify
            self.category = classify(self.name, self.calories, self.protein, self.carbs, self.fat)
        super().save(*args, **kwargs)

    @property
    def emoji(self):
        from .foodicons import emoji_for
        return emoji_for(self.name)

    def __str__(self):
        return self.name


class MealEntry(models.Model):
    MEAL_TYPES = [
        ('breakfast', 'Breakfast'),
        ('lunch', 'Lunch'),
        ('dinner', 'Dinner'),
        ('snack', 'Snack'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    food = models.ForeignKey(Food, on_delete=models.CASCADE)
    quantity_grams = models.FloatField()
    meal_type = models.CharField(max_length=20, choices=MEAL_TYPES)
    date = models.DateField(auto_now_add=False)

    def total_calories(self):
        return round(self.food.calories * self.quantity_grams / 100, 1)

    def total_protein(self):
        return round(self.food.protein * self.quantity_grams / 100, 1)

    def total_carbs(self):
        return round(self.food.carbs * self.quantity_grams / 100, 1)

    def total_fat(self):
        return round(self.food.fat * self.quantity_grams / 100, 1)

    def __str__(self):
        return f"{self.user.username} - {self.food.name} ({self.date})"


class ActivityEntry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    steps = models.IntegerField(default=0)
    calories_burned = models.FloatField(default=0)
    activity_type = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.steps} steps"


class DailyGoal(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    target_calories = models.FloatField(default=2000)
    target_protein = models.FloatField(default=100)
    target_steps = models.IntegerField(default=10000)
    target_water_ml = models.IntegerField(default=2000)

    def __str__(self):
        return f"{self.user.username}'s goals"


class WeightEntry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    weight_kg = models.FloatField()

    class Meta:
        unique_together = ('user', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.weight_kg} kg"


class WaterLog(models.Model):
    """One row per user per day holding the total millilitres drunk."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    amount_ml = models.IntegerField(default=0)

    class Meta:
        unique_together = ('user', 'date')

    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.amount_ml} ml"


class FavoriteFood(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorite_foods')
    food = models.ForeignKey(Food, on_delete=models.CASCADE, related_name='favorited_by')

    class Meta:
        unique_together = ('user', 'food')

    def __str__(self):
        return f"{self.user.username} ♥ {self.food.name}"


class SavedMeal(models.Model):
    """A reusable group of foods, e.g. 'My usual breakfast'."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_meals')
    name = models.CharField(max_length=60)

    class Meta:
        unique_together = ('user', 'name')
        ordering = ['name']

    def __str__(self):
        return self.name

    def totals(self):
        items = list(self.items.select_related('food'))
        return {
            'calories': round(sum(i.food.calories * i.quantity_grams / 100 for i in items), 1),
            'protein': round(sum(i.food.protein * i.quantity_grams / 100 for i in items), 1),
        }


class SavedMealItem(models.Model):
    saved_meal = models.ForeignKey(SavedMeal, on_delete=models.CASCADE, related_name='items')
    food = models.ForeignKey(Food, on_delete=models.CASCADE)
    quantity_grams = models.FloatField()

    def __str__(self):
        return f"{self.food.name} {self.quantity_grams:g} g"


class ApiToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='api_token')
    key = models.CharField(max_length=64, unique=True, default=secrets.token_hex)
    created = models.DateTimeField(auto_now_add=True)

    def regenerate(self):
        self.key = secrets.token_hex(32)
        self.save(update_fields=['key'])

    def __str__(self):
        return f"token for {self.user.username}"


class UserSettings(models.Model):
    """Per-user preferences for notifications and connected services."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='settings')
    weekly_email = models.BooleanField(default=True)
    telegram_chat_id = models.CharField(max_length=32, blank=True)
    telegram_link_code = models.CharField(max_length=32, blank=True)
    reminders_enabled = models.BooleanField(default=False)
    reminder_times = models.CharField(max_length=60, default='08:00,13:00,19:30',
                                      help_text='Comma-separated local times, HH:MM')
    last_reminder_key = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"settings for {self.user.username}"

    @classmethod
    def for_user(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj


class FitbitConnection(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='fitbit')
    fitbit_user_id = models.CharField(max_length=40, blank=True)
    access_token = models.TextField()
    refresh_token = models.TextField()
    expires_at = models.DateTimeField()
    last_synced = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"fitbit for {self.user.username}"
