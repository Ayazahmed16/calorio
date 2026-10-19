# Calorio

A calorie, nutrition and activity tracker built with Django.

## Features
- Meal builder grouped by Protein / Carbs / Fats, saved meals, favorites, food photos and live search
- Activity, weight and water tracking, daily goals, calorie calculator, analytics, streaks
- Per-user custom foods, CSV import/export, JSON API with token auth, installable (PWA)
- Integrations: USDA FoodData Central, Open Food Facts, TheMealDB recipes, Fitbit sync, Telegram reminders, SMTP email

## Run locally
```
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin and shared foods
python manage.py runserver
```
Open http://127.0.0.1:8000/

## Tests
```
python manage.py test tracker --parallel 8
```

## Configuration
All settings come from environment variables; see `.env.example`. Nothing is required for local use.
Set `DJANGO_DEBUG=0` plus `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS` before deploying
(the app refuses to start in production mode with the default key).

## Scheduled jobs (cron / Windows Task Scheduler)
| Command | When | Purpose |
|---|---|---|
| `python manage.py send_reminders` | every 5-10 min | Telegram meal reminders |
| `python manage.py send_weekly_summary` | weekly | Weekly summary emails |
| `python manage.py telegram_poll` | keep running (dev) | Telegram bot replies without a public webhook |
| `python manage.py fetch_food_images` | once | Look up photos for existing foods |

## Notes
- The database is SQLite. Use PostgreSQL for a real deployment.
- Fitbit tokens are stored unencrypted in the database; encrypt them before deploying.
- Serve static files with WhiteNoise or your web server when `DEBUG` is off (`collectstatic`).
