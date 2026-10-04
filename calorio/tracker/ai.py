import json
import os

from google import genai
from google.genai import types

MODEL = os.environ.get('GEMINI_MODEL', 'gemini-3.5-flash-lite')

PARSE_SYSTEM = """You turn a food diary sentence into JSON.
Reply with JSON only, no other text, in this shape:
{"items": [{"food_id": 1, "servings": 2}],
 "unmatched": [{"name": "Pizza slice", "calories": 285, "protein": 12, "carbs": 36, "fat": 10}]}

Rules:
- "items": foods that match one in the list. Use the id from the list. "servings" is a number of the listed serving unit.
- "unmatched": foods not in the list. Give your best estimate of calories, protein, carbs and fat for the whole amount eaten.
- Only use ids from the list. Never invent ids.
- Ignore anything that is not food."""

ESTIMATE_SYSTEM = """You estimate calories for a dish eaten at a restaurant.
Reply with JSON only, no other text, in this shape:
{"name": "Chicken biryani", "calories_low": 650, "calories_mid": 850, "calories_high": 1100,
 "protein": 35, "carbs": 100, "fat": 35, "note": "Short reason for the range."}

Rules:
- Restaurant food varies a lot (oil, ghee, portion size). Give a realistic range, not one number.
- calories_low <= calories_mid <= calories_high.
- protein, carbs and fat (grams) are for the typical (mid) case.
- note is one short sentence on what causes the range.
- If the text is not a food, reply {"error": "not food"}."""

RECIPE_SYSTEM = """You suggest simple recipes from ingredients the user has.
Reply with JSON only, no other text, in this shape:
{"recipes": [{"name": "Spinach egg bhurji", "minutes": 15,
  "ingredients_used": ["eggs", "spinach"], "extra_needed": ["oil", "salt"],
  "calories": 350, "protein": 24, "carbs": 10, "fat": 22,
  "steps": ["Chop the spinach.", "Cook it with the eggs."]}]}

Rules:
- Give 3 different recipes.
- Use mainly the listed ingredients. Basic pantry items (oil, salt, spices, water) are allowed. Put anything else that is not listed in extra_needed.
- calories, protein, carbs and fat (grams) are for ONE serving. Give honest estimates.
- Each recipe must be at most the calorie budget given.
- Try to cover the protein still needed, without going over the calorie budget.
- steps: 3 to 6 short steps.
- If the input is not food ingredients, reply {"recipes": []}."""


def _ask(system, content, max_tokens):
    client = genai.Client()  # reads GEMINI_API_KEY from the environment
    response = client.models.generate_content(
        model=MODEL,
        contents=content,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type='application/json',
            max_output_tokens=max_tokens,
            temperature=0.2,
        ),
    )
    raw = response.text.strip()
    raw = raw.removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    return json.loads(raw)


def parse_meal_text(text, foods):
    food_list = '\n'.join(f'{f.id}: {f.name} ({f.serving_unit})' for f in foods)
    return _ask(PARSE_SYSTEM, f'Food list:\n{food_list}\n\nI ate: {text}', 2000)


def estimate_restaurant_meal(text):
    return _ask(ESTIMATE_SYSTEM, text, 1000)


def suggest_recipes(ingredients, left_cal, left_protein):
    prompt = (
        f"Ingredients I have: {', '.join(ingredients)}\n"
        f"Calorie budget for one serving: {int(left_cal)} kcal\n"
        f"Protein I still need today: {int(left_protein)} g"
    )
    return _ask(RECIPE_SYSTEM, prompt, 3000)