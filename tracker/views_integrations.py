"""Views for the external-service features: Connections page, Fitbit, Telegram, email, and recipes."""
import json
import re
import secrets

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import integrations as ext
from .forms import FIELD
from .models import FitbitConnection, Food, UserSettings

TIME_RE = re.compile(r'^([01]?\d|2[0-3]):[0-5]\d$')


# ============================================================ Connections page

@login_required
def connections(request):
    us = UserSettings.for_user(request.user)
    conn = FitbitConnection.objects.filter(user=request.user).first()
    tg_link = ''
    if us.telegram_link_code and settings.TELEGRAM_BOT_USERNAME:
        tg_link = f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={us.telegram_link_code}'
    return render(request, 'tracker/connections.html', {
        'us': us, 'conn': conn,
        'fitbit_ready': ext.fitbit_configured(),
        'fitbit_redirect': request.build_absolute_uri(reverse('fitbit_callback')),
        'telegram_ready': ext.telegram_configured(),
        'tg_link': tg_link, 'tg_username': settings.TELEGRAM_BOT_USERNAME,
        'smtp_ready': bool(settings.EMAIL_HOST),
        'usda_custom_key': settings.USDA_API_KEY != 'DEMO_KEY',
    })


@login_required
@require_POST
def update_email(request):
    email = request.POST.get('email', '').strip()
    try:
        if email:
            validate_email(email)
    except ValidationError:
        messages.error(request, 'Enter a valid email address.')
        return redirect('connections')
    request.user.email = email
    request.user.save(update_fields=['email'])
    messages.success(request, 'Email saved' if email else 'Email removed')
    return redirect('connections')


@login_required
@require_POST
def send_test_email(request):
    if not request.user.email:
        messages.error(request, 'Save an email address first.')
        return redirect('connections')
    try:
        send_mail('Calorio test email', 'If you can read this, email delivery from Calorio works.',
                  settings.DEFAULT_FROM_EMAIL, [request.user.email], fail_silently=False)
    except Exception as e:      # noqa: BLE001 - SMTP errors vary widely; show the reason to the user
        messages.error(request, f'Could not send email: {e}')
    else:
        where = 'your inbox' if settings.EMAIL_HOST else 'the terminal running the server (no SMTP configured)'
        messages.success(request, f'Test email sent. Check {where}.')
    return redirect('connections')


@login_required
@require_POST
def update_notifications(request):
    us = UserSettings.for_user(request.user)
    times = [t.strip() for t in request.POST.get('reminder_times', '').split(',') if t.strip()]
    if not times or len(times) > 6 or not all(TIME_RE.match(t) for t in times):
        messages.error(request, 'Reminder times must look like 08:00, 13:00, 19:30 (up to 6, 24-hour clock).')
        return redirect('connections')
    us.reminder_times = ','.join(f'{int(t.split(":")[0]):02d}:{t.split(":")[1]}' for t in times)
    us.weekly_email = bool(request.POST.get('weekly_email'))
    us.reminders_enabled = bool(request.POST.get('reminders_enabled')) and bool(us.telegram_chat_id)
    us.save()
    if request.POST.get('reminders_enabled') and not us.telegram_chat_id:
        messages.error(request, 'Connect Telegram first to receive reminders. Other settings were saved.')
    else:
        messages.success(request, 'Notification settings saved')
    return redirect('connections')


# ================================================================== Fitbit

@login_required
def fitbit_connect(request):
    if not ext.fitbit_configured():
        messages.error(request, 'Fitbit is not configured. Set FITBIT_CLIENT_ID and FITBIT_CLIENT_SECRET.')
        return redirect('connections')
    state = secrets.token_urlsafe(24)
    verifier, challenge = ext.new_pkce()
    request.session['fitbit_state'], request.session['fitbit_verifier'] = state, verifier
    redirect_uri = request.build_absolute_uri(reverse('fitbit_callback'))
    return redirect(ext.fitbit_auth_url(redirect_uri, state, challenge))


@login_required
def fitbit_callback(request):
    state = request.session.pop('fitbit_state', '')
    verifier = request.session.pop('fitbit_verifier', '')
    got = request.GET.get('state', '')
    if request.GET.get('error'):
        messages.error(request, 'Fitbit access was not granted.')
        return redirect('connections')
    if not state or not got or not secrets.compare_digest(state, got) or not request.GET.get('code'):
        messages.error(request, 'Fitbit sign-in could not be verified. Please try again.')
        return redirect('connections')
    try:
        tok = ext.fitbit_exchange(request.GET['code'], verifier, request.build_absolute_uri(reverse('fitbit_callback')))
        conn = FitbitConnection.objects.filter(user=request.user).first() or FitbitConnection(user=request.user)
        conn.refresh_token = tok.get('refresh_token', '')
        ext._store_tokens(conn, tok)
        result = ext.fitbit_sync(conn, days=7)
    except ext.ApiError as e:
        messages.error(request, f'Fitbit connection failed: {e}')
        return redirect('connections')
    messages.success(request, f'Fitbit connected. Imported {result["days"]} day(s) of activity and {result["weights"]} weight(s).')
    return redirect('connections')


@login_required
@require_POST
def fitbit_sync(request):
    conn = FitbitConnection.objects.filter(user=request.user).first()
    if not conn:
        messages.error(request, 'Fitbit is not connected.')
        return redirect('connections')
    try:
        days = min(max(int(request.POST.get('days', 7)), 1), 30)
        result = ext.fitbit_sync(conn, days=days)
    except (ext.ApiError, ValueError) as e:
        messages.error(request, f'Fitbit sync failed: {e}')
    else:
        messages.success(request, f'Synced {result["days"]} day(s) of activity and {result["weights"]} weight(s).')
    return redirect('connections')


@login_required
@require_POST
def fitbit_disconnect(request):
    FitbitConnection.objects.filter(user=request.user).delete()
    messages.success(request, 'Fitbit disconnected. Data already imported stays in Calorio.')
    return redirect('connections')


# ================================================================ Telegram

@login_required
@require_POST
def telegram_connect(request):
    if not ext.telegram_configured() or not settings.TELEGRAM_BOT_USERNAME:
        messages.error(request, 'Telegram is not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_USERNAME.')
        return redirect('connections')
    us = UserSettings.for_user(request.user)
    us.telegram_link_code = secrets.token_urlsafe(12)
    us.save(update_fields=['telegram_link_code'])
    messages.success(request, 'Open the Telegram link below and press Start to finish connecting.')
    return redirect('connections')


@login_required
@require_POST
def telegram_disconnect(request):
    us = UserSettings.for_user(request.user)
    us.telegram_chat_id, us.telegram_link_code, us.reminders_enabled = '', '', False
    us.save()
    messages.success(request, 'Telegram disconnected.')
    return redirect('connections')


@login_required
@require_POST
def telegram_test(request):
    us = UserSettings.for_user(request.user)
    if not us.telegram_chat_id:
        messages.error(request, 'Telegram is not connected.')
    elif ext.tg_send(us.telegram_chat_id, 'Hello from Calorio! Reminders and /today will arrive here.'):
        messages.success(request, 'Test message sent to Telegram.')
    else:
        messages.error(request, 'Telegram did not accept the message. Check the bot token.')
    return redirect('connections')


@csrf_exempt
@require_POST
def telegram_webhook(request, secret):
    """Telegram calls this when users message the bot. The URL secret authenticates Telegram."""
    expected = settings.TELEGRAM_WEBHOOK_SECRET
    if not expected or not secrets.compare_digest(secret, expected):
        return HttpResponseNotFound()
    try:
        update = json.loads(request.body or b'{}')
    except ValueError:
        return HttpResponse(status=400)
    if isinstance(update, dict):
        ext.tg_handle_update(update)
    return HttpResponse('ok')


# ================================================================= Recipes

class RecipeFoodForm(forms.Form):
    """TheMealDB has no nutrition data, so the user supplies per-serving values."""
    name = forms.CharField(max_length=100, widget=forms.TextInput(attrs=FIELD))
    serving_g = forms.FloatField(min_value=10, max_value=3000, label='Serving size (g)',
                                 widget=forms.NumberInput(attrs={**FIELD, 'step': '1'}))
    calories = forms.FloatField(min_value=0, max_value=5000, label='Calories per serving',
                                widget=forms.NumberInput(attrs={**FIELD, 'step': '1'}))
    protein = forms.FloatField(min_value=0, max_value=500, label='Protein per serving (g)',
                               widget=forms.NumberInput(attrs={**FIELD, 'step': '0.1'}))
    carbs = forms.FloatField(min_value=0, max_value=800, label='Carbs per serving (g)',
                             widget=forms.NumberInput(attrs={**FIELD, 'step': '0.1'}))
    fat = forms.FloatField(min_value=0, max_value=500, label='Fat per serving (g)',
                           widget=forms.NumberInput(attrs={**FIELD, 'step': '0.1'}))

    def clean(self):
        d = super().clean()
        if all(d.get(k) is not None for k in ('serving_g', 'protein', 'carbs', 'fat')):
            if d['protein'] + d['carbs'] + d['fat'] > d['serving_g']:
                raise forms.ValidationError('Protein + carbs + fat cannot weigh more than the serving itself.')
        return d


@login_required
def recipes(request):
    q = request.GET.get('q', '').strip()[:60]
    category = request.GET.get('category', '').strip()[:40]
    error, results, categories = '', [], []
    try:
        categories = ext.meal_categories()
        if q:
            results = ext.meal_search(q)
        elif category in categories:
            results = ext.meal_by_category(category)
        else:
            category = ''
            results = ext.meal_random() + ext.meal_random() + ext.meal_random() + ext.meal_random()
            seen, uniq = set(), []
            for r in results:
                if r['id'] not in seen:
                    seen.add(r['id'])
                    uniq.append(r)
            results = uniq
    except ext.ApiError:
        error = 'The recipe service (TheMealDB) is unreachable right now. Please try again in a moment.'
    return render(request, 'tracker/recipes.html', {
        'results': results, 'q': q, 'category': category, 'categories': categories, 'error': error,
        'featured': not q and not category,
    })


@login_required
def recipe_detail(request, meal_id):
    try:
        recipe = ext.meal_detail(meal_id)
    except ext.ApiError:
        messages.error(request, 'The recipe service is unreachable right now.')
        return redirect('recipes')
    if not recipe:
        messages.error(request, 'Recipe not found.')
        return redirect('recipes')
    form = RecipeFoodForm(request.POST or None, initial={'name': recipe['name'], 'serving_g': 350})
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        k = 100 / d['serving_g']
        name = d['name'].strip()
        if Food.objects.visible_to(request.user).filter(name__iexact=name).exists():
            form.add_error('name', 'You already have a food with this name. Choose another name.')
        else:
            food = Food.objects.create(
                name=name, calories=round(d['calories'] * k, 1), protein=round(d['protein'] * k, 1),
                carbs=round(d['carbs'] * k, 1), fat=round(d['fat'] * k, 1),
                owner=None if request.user.is_staff else request.user, image_url=recipe['image'])
            messages.success(request, f'Saved "{food.name}" to your foods.')
            return redirect(f"{reverse('add_meal')}?food={food.id}&qty={d['serving_g']:g}")
    return render(request, 'tracker/recipe_detail.html', {'r': recipe, 'form': form})
