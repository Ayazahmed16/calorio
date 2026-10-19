"""Group foods into Protein / Carbs / Fats for the meal builder (anything else is 'other')."""

GROUPS = [
    ('protein', 'Protein', 'Meat, fish, eggs, dairy, legumes...'),
    ('carbs', 'Carbs', 'Rice, bread, pasta, potatoes, fruit...'),
    ('fats', 'Fats', 'Oils, butter, nuts, seeds, avocado...'),
]
CATEGORY_CHOICES = [(k, label) for k, label, _ in GROUPS] + [('other', 'Other')]

# Keywords win over macros because "peanut butter" or "cooked rice" read more reliably from the name.
_KEYWORDS = {
    'fats': ('oil', 'butter', 'ghee', 'lard', 'mayonnaise', 'mayo', 'almond', 'walnut', 'cashew', 'pistachio',
             'hazelnut', 'peanut', 'nut ', 'nuts', 'seed', 'tahini', 'avocado', 'coconut', 'olive', 'cream', 'bacon'),
    'protein': ('chicken', 'turkey', 'beef', 'steak', 'pork', 'lamb', 'mutton', 'meat', 'ham', 'fish', 'salmon', 'tuna',
                'sardine', 'cod', 'shrimp', 'prawn', 'crab', 'egg', 'tofu', 'tempeh', 'paneer', 'whey', 'protein',
                'lentil', 'dal', 'chickpea', 'bean', 'yogurt', 'yoghurt', 'cottage', 'milk', 'sausage'),
    'carbs': ('rice', 'bread', 'toast', 'pasta', 'spaghetti', 'noodle', 'macaroni', 'potato', 'oat', 'cereal', 'granola',
              'roti', 'chapati', 'naan', 'tortilla', 'wheat', 'flour', 'quinoa', 'couscous', 'corn', 'sugar', 'honey',
              'banana', 'apple', 'mango', 'orange', 'grape', 'bagel', 'cracker', 'biscuit', 'cookie', 'cake', 'juice'),
}


def classify(name, calories=0, protein=0, carbs=0, fat=0):
    n = f' {(name or "").lower()} '
    # peanut/almond *butter* is a fat; "butter chicken" would still match fats first, which is acceptable for a guess
    for cat in ('fats', 'protein', 'carbs'):
        if any(k in n for k in _KEYWORDS[cat]):
            return cat
    p, c, f = (protein or 0) * 4, (carbs or 0) * 4, (fat or 0) * 9
    if (calories or 0) < 40 and p + c + f < 160:
        return 'other'                                # vegetables, water, tea
    if max(p, c, f) == 0:
        return 'other'
    return max((('protein', p), ('carbs', c), ('fats', f)), key=lambda kv: kv[1])[0]
