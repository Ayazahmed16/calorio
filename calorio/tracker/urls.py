from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from . import views
from .api_views import (
    MealViewSet, ActivityViewSet, SummaryView, FoodViewSet,
    ParseMealView, EstimateMealView, BarcodeView,
)
from .suggest_view import GoalView, SuggestionView
from .recipe_view import RecipeView
from .streak_view import StreakView
from .challenge_view import ChallengeListView, ChallengeDetailView, JoinView, LeaveView
from .report_view import WeeklyReportView, ReportSettingsView

router = DefaultRouter()
router.register('meals', MealViewSet, basename='meal')
router.register('activities', ActivityViewSet, basename='activity')
router.register('foods', FoodViewSet, basename='food')

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('add/', views.add_meal, name='add_meal'),
    path('register/', views.register, name='register'),
    path('api/token/', obtain_auth_token, name='api_token'),
    path('api/summary/', SummaryView.as_view(), name='api_summary'),
    path('api/parse-meal/', ParseMealView.as_view(), name='api_parse_meal'),
    path('api/estimate-meal/', EstimateMealView.as_view(), name='api_estimate_meal'),
    path('api/barcode/<str:code>/', BarcodeView.as_view(), name='api_barcode'),
    path('api/goal/', GoalView.as_view(), name='api_goal'),
    path('api/suggestions/', SuggestionView.as_view(), name='api_suggestions'),
    path('api/recipes/', RecipeView.as_view(), name='api_recipes'),
    path('api/streaks/', StreakView.as_view(), name='api_streaks'),
    path('api/challenges/', ChallengeListView.as_view(), name='api_challenges'),
    path('api/challenges/join/', JoinView.as_view(), name='api_challenge_join'),
    path('api/challenges/<int:pk>/', ChallengeDetailView.as_view(), name='api_challenge'),
    path('api/challenges/<int:pk>/leave/', LeaveView.as_view(), name='api_challenge_leave'),
    path('api/report/weekly/', WeeklyReportView.as_view(), name='api_report_weekly'),
    path('api/report/settings/', ReportSettingsView.as_view(), name='api_report_settings'),
    path('api/', include(router.urls)),
]