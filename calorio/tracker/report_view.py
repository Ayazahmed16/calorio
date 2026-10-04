from django.http import HttpResponse
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import ReportPref
from .reports import build_pdf, week_data


class WeeklyReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'report'

    def get(self, request):
        pdf = build_pdf(request.user, week_data(request.user))
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="calorio-weekly-report.pdf"'
        return response


class ReportSettingsSerializer(serializers.Serializer):
    email = serializers.EmailField(allow_blank=True, max_length=254)
    weekly_email = serializers.BooleanField()

    def validate(self, data):
        if data['weekly_email'] and not data['email']:
            raise serializers.ValidationError('Add an email address to get the weekly report.')
        return data


class ReportSettingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pref, _ = ReportPref.objects.get_or_create(user=request.user)
        return Response({'email': request.user.email, 'weekly_email': pref.weekly_email})

    def put(self, request):
        serializer = ReportSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pref, _ = ReportPref.objects.get_or_create(user=request.user)
        request.user.email = serializer.validated_data['email']
        request.user.save(update_fields=['email'])
        pref.weekly_email = serializer.validated_data['weekly_email']
        pref.save()
        return Response(serializer.validated_data)