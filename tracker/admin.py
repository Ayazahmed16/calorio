from django.contrib import admin
from .models import Food, MealEntry, ActivityEntry, DailyGoal


@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    list_display = ('name', 'calories', 'protein', 'carbs', 'fat')
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(MealEntry)
class MealEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'food', 'quantity_grams', 'meal_type', 'date')
    list_filter = ('meal_type', 'date')
    search_fields = ('user__username', 'food__name')
    date_hierarchy = 'date'


@admin.register(ActivityEntry)
class ActivityEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'steps', 'calories_burned', 'activity_type')
    list_filter = ('date',)
    search_fields = ('user__username', 'activity_type')
    date_hierarchy = 'date'


@admin.register(DailyGoal)
class DailyGoalAdmin(admin.ModelAdmin):
    list_display = ('user', 'target_calories', 'target_protein', 'target_steps')
    search_fields = ('user__username',)
