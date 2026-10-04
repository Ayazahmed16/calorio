from django.shortcuts import redirect, render
from django.contrib.auth import login
from .models import Meal, Activity
from .forms import MealForm
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth. decorators import login_required
from django.db.models import Sum 
from django.db.models.functions import TruncDate
from django.utils import timezone

@login_required
def dashboard(request):
    today = timezone.localdate()
    meals = Meal.objects.filter(user = request.user)
    activities = Activity.objects.filter(user = request.user)
    
    today_totals =meals.filter(eaten_at__date=today).aggregate(calories=Sum('calories'), protein=Sum('protein'))
    today_steps = activities.filter(date=today).aggregate(steps=Sum('steps'))
    
    
    daily = (
        meals
        .annotate(day= TruncDate('eaten_at'))
        .values('day')
        .annotate(calories=Sum('calories'), protein =Sum('protein'))
        .order_by('-day')
    )


    
    context = {
        'meals': meals.order_by('-eaten_at')[:10],
        'activities': activities.order_by('-date')[:10],
        'today_calories' : today_totals['calories'] or 0,
        'today_protein' : today_totals['protein'] or 0,
        'today_steps' : today_steps['steps'] or 0,
        'daily' : daily,
    }
    return render(request, 'tracker/dashboard.html', context)

@login_required
def add_meal(request):
    if request.method == 'POST':
        form = MealForm(request.POST)    
        if form.is_valid():  
            meal= form.save(commit=False)
            meal.user = request.user
            meal.save()
            return redirect('dashboard') 
    else:
        form = MealForm()          
    return render(request, 'tracker/add_meal.html', {'form': form})

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})