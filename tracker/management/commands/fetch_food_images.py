import time

from django.core.management.base import BaseCommand

from tracker.models import Food
from tracker.services import find_food_image


class Command(BaseCommand):
    help = 'Look up photos (Wikipedia) for foods that do not have one yet. Foods without a match keep their emoji.'

    def handle(self, *args, **opts):
        found = checked = 0
        for food in Food.objects.filter(image_url=''):
            checked += 1
            url = find_food_image(food.name)
            if url:
                food.image_url = url
                food.save(update_fields=['image_url'])
                found += 1
                self.stdout.write(f'  {food.name}: found')
            time.sleep(0.3)           # be polite to the API
        self.stdout.write(self.style.SUCCESS(f'Checked {checked} food(s), found {found} photo(s)'))
