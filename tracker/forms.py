from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .foodcategory import CATEGORY_CHOICES
from .models import ActivityEntry, DailyGoal, Food, MealEntry, SavedMeal, WeightEntry

FIELD = {'class': 'field'}


class MealForm(forms.ModelForm):
    class Meta:
        model = MealEntry
        fields = ['food', 'quantity_grams', 'meal_type', 'date']
        labels = {'quantity_grams': 'Quantity (grams)', 'meal_type': 'Meal type'}
        widgets = {
            'food': forms.Select(attrs=FIELD),
            'quantity_grams': forms.NumberInput(attrs={**FIELD, 'step': '0.1', 'min': '0.1'}),
            'meal_type': forms.Select(attrs=FIELD),
            'date': forms.DateInput(attrs={**FIELD, 'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        foods = Food.objects.visible_to(user) if user is not None else Food.objects.all()
        self.fields['food'].queryset = foods.order_by('name')
        self.fields['food'].empty_label = 'Select a food'
        if not self.instance.pk:
            self.fields['date'].initial = timezone.localdate()

    def clean_quantity_grams(self):
        q = self.cleaned_data['quantity_grams']
        if q <= 0:
            raise forms.ValidationError('Quantity must be greater than zero.')
        if q > 5000:
            raise forms.ValidationError('That looks too large. Maximum is 5000 g.')
        return q

    def clean_date(self):
        d = self.cleaned_data['date']
        if d > timezone.localdate():
            raise forms.ValidationError('You cannot log a meal in the future.')
        return d


class ActivityForm(forms.ModelForm):
    class Meta:
        model = ActivityEntry
        fields = ['steps', 'calories_burned', 'activity_type', 'date']
        labels = {'calories_burned': 'Calories burned', 'activity_type': 'Activity type (optional)'}
        widgets = {
            'steps': forms.NumberInput(attrs={**FIELD, 'min': '0'}),
            'calories_burned': forms.NumberInput(attrs={**FIELD, 'step': '0.1', 'min': '0'}),
            'activity_type': forms.TextInput(attrs=FIELD),
            'date': forms.DateInput(attrs={**FIELD, 'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['date'].initial = timezone.localdate()
            # start empty (not "0") so typing never appends to a pre-filled zero
            self.fields['steps'].initial = None
            self.fields['calories_burned'].initial = None
            self.fields['steps'].widget.attrs['placeholder'] = '0'
            self.fields['calories_burned'].widget.attrs['placeholder'] = '0'

    def clean_steps(self):
        v = self.cleaned_data['steps']
        if v < 0 or v > 200000:
            raise forms.ValidationError('Steps must be between 0 and 200,000.')
        return v

    def clean_calories_burned(self):
        v = self.cleaned_data['calories_burned']
        if v < 0 or v > 20000:
            raise forms.ValidationError('Calories burned must be between 0 and 20,000.')
        return v

    def clean_date(self):
        d = self.cleaned_data['date']
        if d > timezone.localdate():
            raise forms.ValidationError('You cannot log activity in the future.')
        return d


class FoodForm(forms.ModelForm):
    class Meta:
        model = Food
        fields = ['name', 'category', 'calories', 'protein', 'carbs', 'fat', 'barcode', 'image_url']
        labels = {
            'calories': 'Calories (per 100 g)',
            'protein': 'Protein (g per 100 g)',
            'carbs': 'Carbs (g per 100 g)',
            'fat': 'Fat (g per 100 g)',
            'barcode': 'Barcode (optional)',
            'category': 'Group (protein / carbs / fats)',
            'image_url': 'Photo URL (optional, https)',
        }
        widgets = {
            'barcode': forms.TextInput(attrs=FIELD),
            'category': forms.Select(attrs=FIELD),
            'image_url': forms.URLInput(attrs={**FIELD, 'placeholder': 'Leave empty to look one up automatically'}),
            'name': forms.TextInput(attrs=FIELD),
            'calories': forms.NumberInput(attrs={**FIELD, 'step': '0.1', 'min': '0'}),
            'protein': forms.NumberInput(attrs={**FIELD, 'step': '0.1', 'min': '0'}),
            'carbs': forms.NumberInput(attrs={**FIELD, 'step': '0.1', 'min': '0'}),
            'fat': forms.NumberInput(attrs={**FIELD, 'step': '0.1', 'min': '0'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['barcode'].required = False
        self.fields['category'].required = False
        self.fields['category'].choices = [('', 'Auto-detect from name and macros')] + CATEGORY_CHOICES
        self.fields['image_url'].required = False

    def clean(self):
        data = super().clean()
        for name in ('calories', 'protein', 'carbs', 'fat'):
            v = data.get(name)
            if v is not None and v < 0:
                self.add_error(name, 'Cannot be negative.')
        if all(data.get(n) is not None for n in ('protein', 'carbs', 'fat')):
            if data['protein'] + data['carbs'] + data['fat'] > 100:
                raise forms.ValidationError('Protein + carbs + fat cannot exceed 100 g per 100 g of food.')
        return data

    def clean_image_url(self):
        url = (self.cleaned_data.get('image_url') or '').strip()
        if url and not url.startswith('https://'):
            raise forms.ValidationError('Photo links must start with https://')
        return url

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        visible = Food.objects.visible_to(self.user) if self.user is not None else Food.objects.all()
        qs = visible.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('A food with this name already exists.')
        return name


class GoalForm(forms.ModelForm):
    class Meta:
        model = DailyGoal
        fields = ['target_calories', 'target_protein', 'target_steps', 'target_water_ml']
        labels = {
            'target_calories': 'Daily calories',
            'target_protein': 'Daily protein (g)',
            'target_steps': 'Daily steps',
            'target_water_ml': 'Daily water (ml)',
        }
        widgets = {
            'target_calories': forms.NumberInput(attrs={**FIELD, 'min': '500', 'max': '10000'}),
            'target_protein': forms.NumberInput(attrs={**FIELD, 'min': '10', 'max': '500'}),
            'target_steps': forms.NumberInput(attrs={**FIELD, 'min': '1000', 'max': '100000'}),
            'target_water_ml': forms.NumberInput(attrs={**FIELD, 'min': '500', 'max': '10000', 'step': '50'}),
        }

    def _range(self, name, lo, hi, label):
        v = self.cleaned_data[name]
        if not lo <= v <= hi:
            raise forms.ValidationError(f'{label} must be between {lo:,} and {hi:,}.')
        return v

    def clean_target_calories(self):
        return self._range('target_calories', 500, 10000, 'Calories')

    def clean_target_protein(self):
        return self._range('target_protein', 10, 500, 'Protein')

    def clean_target_steps(self):
        return self._range('target_steps', 1000, 100000, 'Steps')

    def clean_target_water_ml(self):
        return self._range('target_water_ml', 500, 10000, 'Water')


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs=FIELD))

    class Meta:
        model = User
        fields = ['username', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', 'field')
        self.fields['username'].help_text = ''
        self.fields['password1'].help_text = ''
        self.fields['password2'].help_text = ''


class WeightForm(forms.ModelForm):
    class Meta:
        model = WeightEntry
        fields = ['date', 'weight_kg']
        labels = {'weight_kg': 'Weight (kg)'}
        widgets = {
            'date': forms.DateInput(attrs={**FIELD, 'type': 'date'}, format='%Y-%m-%d'),
            'weight_kg': forms.NumberInput(attrs={**FIELD, 'step': '0.1', 'min': '20', 'max': '400'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['date'].initial = timezone.localdate()

    def validate_unique(self):
        # the view upserts one row per day, so the unique_together check is handled there
        pass

    def clean_weight_kg(self):
        v = self.cleaned_data['weight_kg']
        if not 20 <= v <= 400:
            raise forms.ValidationError('Weight must be between 20 and 400 kg.')
        return round(v, 1)

    def clean_date(self):
        d = self.cleaned_data['date']
        if d > timezone.localdate():
            raise forms.ValidationError('You cannot log a future date.')
        return d


class WaterForm(forms.Form):
    amount_ml = forms.IntegerField(min_value=-5000, max_value=5000)
    date = forms.DateField(required=False)

    def clean_amount_ml(self):
        v = self.cleaned_data['amount_ml']
        if v == 0:
            raise forms.ValidationError('Enter a non-zero amount.')
        return v


class SavedMealForm(forms.Form):
    """Create a saved meal from foods already logged on a day."""
    name = forms.CharField(max_length=60, widget=forms.TextInput(attrs=FIELD), label='Name')
    date = forms.DateField(widget=forms.DateInput(attrs={**FIELD, 'type': 'date'}, format='%Y-%m-%d'),
                           label='Copy from date')
    meal_type = forms.ChoiceField(choices=MealEntry.MEAL_TYPES, widget=forms.Select(attrs=FIELD), label='Meal type')

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['date'].initial = timezone.localdate()

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if SavedMeal.objects.filter(user=self.user, name__iexact=name).exists():
            raise forms.ValidationError('You already have a saved meal with this name.')
        return name

    def clean(self):
        data = super().clean()
        if self.user and data.get('date') and data.get('meal_type'):
            if not MealEntry.objects.filter(user=self.user, date=data['date'], meal_type=data['meal_type']).exists():
                raise forms.ValidationError('No foods are logged for that meal type on that date.')
        return data


class LogSavedMealForm(forms.Form):
    meal_type = forms.ChoiceField(choices=MealEntry.MEAL_TYPES)
    date = forms.DateField(required=False)

    def clean_date(self):
        d = self.cleaned_data.get('date') or timezone.localdate()
        if d > timezone.localdate():
            raise forms.ValidationError('You cannot log in the future.')
        return d


class CalculatorForm(forms.Form):
    SEX = [('male', 'Male'), ('female', 'Female')]
    ACTIVITY = [
        ('1.2', 'Sedentary (little or no exercise)'),
        ('1.375', 'Light (1-3 days/week)'),
        ('1.55', 'Moderate (3-5 days/week)'),
        ('1.725', 'Very active (6-7 days/week)'),
        ('1.9', 'Extra active (physical job + training)'),
    ]
    GOAL = [('lose', 'Lose weight'), ('maintain', 'Maintain weight'), ('gain', 'Gain weight')]

    sex = forms.ChoiceField(choices=SEX, widget=forms.Select(attrs=FIELD))
    age = forms.IntegerField(min_value=14, max_value=100, widget=forms.NumberInput(attrs=FIELD))
    height_cm = forms.FloatField(min_value=100, max_value=250, label='Height (cm)',
                                 widget=forms.NumberInput(attrs={**FIELD, 'step': '0.1'}))
    weight_kg = forms.FloatField(min_value=30, max_value=300, label='Weight (kg)',
                                 widget=forms.NumberInput(attrs={**FIELD, 'step': '0.1'}))
    activity = forms.ChoiceField(choices=ACTIVITY, label='Activity level', widget=forms.Select(attrs=FIELD))
    goal = forms.ChoiceField(choices=GOAL, widget=forms.Select(attrs=FIELD))


class CsvImportForm(forms.Form):
    KINDS = [('meals', 'Meals'), ('activity', 'Activity'), ('weight', 'Weight')]
    kind = forms.ChoiceField(choices=KINDS, widget=forms.Select(attrs=FIELD), label='What are you importing?')
    file = forms.FileField(label='CSV file', widget=forms.ClearableFileInput(attrs={'accept': '.csv', 'class': 'field'}))

    def clean_file(self):
        f = self.cleaned_data['file']
        if f.size > 2 * 1024 * 1024:
            raise forms.ValidationError('File is too large (2 MB maximum).')
        return f


class MealHeaderForm(forms.Form):
    """Meal type and date for the multi-food meal builder."""
    meal_type = forms.ChoiceField(choices=MealEntry.MEAL_TYPES, label='Meal type', widget=forms.Select(attrs=FIELD))
    date = forms.DateField(label='Date', widget=forms.DateInput(attrs={**FIELD, 'type': 'date'}, format='%Y-%m-%d'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].initial = timezone.localdate()

    def clean_date(self):
        d = self.cleaned_data['date']
        if d > timezone.localdate():
            raise forms.ValidationError('You cannot log a meal in the future.')
        return d
