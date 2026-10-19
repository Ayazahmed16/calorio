from django.urls import path
from . import api, views, views_integrations as vi, views_more

urlpatterns = [
    path('', views.landing, name='landing'),
    path('dashboard/', views.dashboard, name='dashboard'),

    path('meals/', views.meal_list, name='meal_list'),
    path('meals/add/', views.add_meal, name='add_meal'),
    path('meals/<int:pk>/edit/', views.edit_meal, name='edit_meal'),
    path('meals/<int:pk>/delete/', views.delete_meal, name='delete_meal'),

    path('activity/', views.activity_list, name='activity_list'),
    path('activity/add/', views.add_activity, name='add_activity'),
    path('activity/<int:pk>/edit/', views.edit_activity, name='edit_activity'),
    path('activity/<int:pk>/delete/', views.delete_activity, name='delete_activity'),

    path('foods/', views.food_list, name='food_list'),
    path('foods/add/', views.add_food, name='add_food'),
    path('foods/lookup/', views_more.food_lookup, name='food_lookup'),
    path('foods/<int:pk>/edit/', views.edit_food, name='edit_food'),
    path('foods/<int:pk>/delete/', views.delete_food, name='delete_food'),
    path('foods/<int:pk>/favorite/', views.toggle_favorite, name='toggle_favorite'),

    path('saved/', views_more.saved_meals, name='saved_meals'),
    path('saved/<int:pk>/log/', views_more.log_saved_meal, name='log_saved_meal'),
    path('saved/<int:pk>/delete/', views_more.delete_saved_meal, name='delete_saved_meal'),

    path('weight/', views_more.weight, name='weight'),
    path('weight/<int:pk>/delete/', views_more.delete_weight, name='delete_weight'),
    path('water/add/', views_more.add_water, name='add_water'),

    path('goals/', views.goals, name='goals'),
    path('calculator/', views_more.calculator, name='calculator'),
    path('analytics/', views.analytics, name='analytics'),

    path('account/', views_more.account, name='account'),
    path('account/token/', views_more.regenerate_token, name='regenerate_token'),
    path('account/export/<str:kind>.csv', views_more.export_csv, name='export_csv'),
    path('account/import/', views_more.import_csv, name='import_csv'),

    path('connections/', vi.connections, name='connections'),
    path('connections/email/', vi.update_email, name='update_email'),
    path('connections/email/test/', vi.send_test_email, name='send_test_email'),
    path('connections/notifications/', vi.update_notifications, name='update_notifications'),
    path('connections/fitbit/connect/', vi.fitbit_connect, name='fitbit_connect'),
    path('connections/fitbit/callback/', vi.fitbit_callback, name='fitbit_callback'),
    path('connections/fitbit/sync/', vi.fitbit_sync, name='fitbit_sync'),
    path('connections/fitbit/disconnect/', vi.fitbit_disconnect, name='fitbit_disconnect'),
    path('connections/telegram/connect/', vi.telegram_connect, name='telegram_connect'),
    path('connections/telegram/disconnect/', vi.telegram_disconnect, name='telegram_disconnect'),
    path('connections/telegram/test/', vi.telegram_test, name='telegram_test'),
    path('telegram/webhook/<str:secret>/', vi.telegram_webhook, name='telegram_webhook'),

    path('recipes/', vi.recipes, name='recipes'),
    path('recipes/<str:meal_id>/', vi.recipe_detail, name='recipe_detail'),

    # JSON API
    path('api/v1/summary/', api.summary, name='api_summary'),
    path('api/v1/meals/', api.meals, name='api_meals'),
    path('api/v1/meals/<int:pk>/', api.meal_detail, name='api_meal_detail'),
    path('api/v1/activity/', api.activity, name='api_activity'),
    path('api/v1/weight/', api.weight, name='api_weight'),
    path('api/v1/water/', api.water, name='api_water'),
    path('api/v1/foods/', api.foods, name='api_foods'),

    # installable app
    path('manifest.webmanifest', views_more.manifest, name='manifest'),
    path('sw.js', views_more.service_worker, name='service_worker'),
    path('offline/', views_more.offline, name='offline'),
]
