from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .gamification import award_badges
from .live import notify_challenges
from .models import Activity, Challenge, Meal


@receiver(post_save, sender=Meal)
@receiver(post_save, sender=Activity)
def update_badges(sender, instance, **kwargs):
    if instance.user_id:
        award_badges(instance.user)


@receiver(post_save, sender=Meal)
@receiver(post_save, sender=Activity)
@receiver(post_delete, sender=Meal)
@receiver(post_delete, sender=Activity)
def push_live_update(sender, instance, **kwargs):
    if instance.user_id:
        ids = Challenge.objects.filter(members__id=instance.user_id).values_list('id', flat=True)
        notify_challenges(list(ids))


@receiver(m2m_changed, sender=Challenge.members.through)
def members_changed(sender, instance, action, reverse, **kwargs):
    # someone joined or left (instance is the Challenge)
    if action in ('post_add', 'post_remove') and not reverse:
        notify_challenges([instance.pk])