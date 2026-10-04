from itertools import combinations

SERVING_OPTIONS = (1, 2)
MIN_MEAL_CALORIES = 100


def score_meal(calories, protein, left_cal, left_protein):
    """Lower is better. 0 means the meal uses up your remaining budget exactly."""
    calorie_gap = (left_cal - calories) / left_cal
    if left_protein > 0:
        protein_gap = max(0.0, left_protein - protein) / left_protein
    else:
        protein_gap = 0.0
    return 0.5 * calorie_gap + 0.5 * protein_gap


def suggest_meals(foods, left_cal, left_protein, limit=3):
    if left_cal <= 0:
        return []

    # every (food, servings) choice, then single choices and pairs of different foods
    options = [(f, s) for f in foods for s in SERVING_OPTIONS]
    combos = [(o,) for o in options]
    combos += [p for p in combinations(options, 2) if p[0][0].id != p[1][0].id]

    scored = []
    for combo in combos:
        calories = sum(f.calories * s for f, s in combo)
        if calories > left_cal or calories < MIN_MEAL_CALORIES:
            continue  # must fit your budget, and be a real meal
        protein = sum(f.protein * s for f, s in combo)
        scored.append((
            score_meal(calories, protein, left_cal, left_protein),
            {
                'items': [{'food': f, 'servings': s} for f, s in combo],
                'calories': calories,
                'protein': protein,
                'carbs': sum(f.carbs * s for f, s in combo),
                'fat': sum(f.fat * s for f, s in combo),
            },
        ))

    scored.sort(key=lambda x: x[0])

    # keep the best one for each set of foods, so you don't see "Roti x1" and "Roti x2"
    results, seen = [], set()
    for _, meal in scored:
        key = frozenset(it['food'].id for it in meal['items'])
        if key in seen:
            continue
        seen.add(key)
        results.append(meal)
        if len(results) == limit:
            break
    return results