from django.contrib import admin
from django.urls import path, include, reverse_lazy
from django.contrib.auth import views as auth_views
from django.contrib.messages.views import SuccessMessageMixin

from tracker.views import signup


CARD = 'registration/auth_card.html'


class PasswordChange(SuccessMessageMixin, auth_views.PasswordChangeView):
    template_name = 'tracker/form_page.html'
    success_url = reverse_lazy('dashboard')
    success_message = 'Password changed'
    extra_context = {
        'title': 'Change Password', 'eyebrow': 'Account', 'crumb': 'Password',
        'submit': 'Update Password', 'cancel_url': reverse_lazy('dashboard'),
    }

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for f in form.fields.values():
            f.widget.attrs['class'] = 'field'
            f.help_text = ''
        return form


urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/signup/', signup, name='signup'),
    path('accounts/password/', PasswordChange.as_view(), name='password_change'),

    path('accounts/password-reset/', auth_views.PasswordResetView.as_view(
        template_name=CARD, email_template_name='registration/password_reset_email.txt',
        extra_context={'title': 'Reset Password', 'eyebrow': 'Account', 'submit': 'Send Reset Link',
                       'message': 'Enter your account email and we will send you a link to choose a new password.'}),
        name='password_reset'),
    path('accounts/password-reset/sent/', auth_views.PasswordResetDoneView.as_view(
        template_name=CARD,
        extra_context={'title': 'Check Your Email', 'eyebrow': 'Account',
                       'message': 'If an account exists for that email, a reset link is on its way.'}),
        name='password_reset_done'),
    path('accounts/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name=CARD,
        extra_context={'title': 'Choose a New Password', 'eyebrow': 'Account', 'submit': 'Save Password'}),
        name='password_reset_confirm'),
    path('accounts/reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name=CARD,
        extra_context={'title': 'Password Updated', 'eyebrow': 'Account',
                       'message': 'Your password has been changed. You can now log in.'}),
        name='password_reset_complete'),
    path('', include('tracker.urls')),
]
