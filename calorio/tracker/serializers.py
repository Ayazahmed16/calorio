from rest_framework import serializers
from .models import Meal, Activity, Food


class FoodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Food
        fields = ['id', 'name', 'serving_unit', 'calories', 'protein', 'carbs', 'fat']


class MealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meal
        fields = ['id', 'food', 'servings', 'meal_type', 'name',
                  'calories', 'protein', 'carbs', 'fat', 'eaten_at']
        read_only_fields = ['eaten_at']
        extra_kwargs = {
            'name': {'required': False},
            'calories': {'required': False},
        }

    def validate_food(self, food):
        user = self.context['request'].user
        if food and food.user_id not in (None, user.id):
            raise serializers.ValidationError('Food not found.')
        return food

    def validate(self, data):
        food = data.get('food')
        if food:
            s = data.get('servings', 1)
            data['name'] = food.name
            data['calories'] = round(food.calories * s)
            data['protein'] = round(food.protein * s, 1)
            data['carbs'] = round(food.carbs * s, 1)
            data['fat'] = round(food.fat * s, 1)
        elif not self.partial and ('name' not in data or 'calories' not in data):
            raise serializers.ValidationError('Provide a food, or a name and calories.')
        return data


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = ['id', 'date', 'steps']