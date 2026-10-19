"""Emoji fallbacks for foods that have no photo. First matching keyword wins, so specific words come first."""

_ICONS = [
    ('pizza', '🍕'), ('burger', '🍔'), ('hamburger', '🍔'), ('hot dog', '🌭'), ('fries', '🍟'), ('taco', '🌮'),
    ('burrito', '🌯'), ('sandwich', '🥪'), ('sushi', '🍣'), ('ramen', '🍜'), ('noodle', '🍜'), ('spaghetti', '🍝'),
    ('pasta', '🍝'), ('macaroni', '🍝'), ('curry', '🍛'), ('biryani', '🍛'), ('rice', '🍚'), ('salad', '🥗'),
    ('soup', '🍲'), ('stew', '🍲'), ('egg', '🥚'), ('omelette', '🍳'), ('bacon', '🥓'), ('steak', '🥩'), ('beef', '🥩'),
    ('lamb', '🥩'), ('mutton', '🥩'), ('pork', '🥩'), ('ham', '🍖'), ('chicken', '🍗'), ('turkey', '🍗'),
    ('fish', '🐟'), ('salmon', '🐟'), ('tuna', '🐟'), ('shrimp', '🍤'), ('prawn', '🍤'), ('crab', '🦀'),
    ('lobster', '🦞'), ('bread', '🍞'), ('toast', '🍞'), ('bagel', '🥯'), ('croissant', '🥐'), ('pancake', '🥞'),
    ('waffle', '🧇'), ('cheese', '🧀'), ('butter', '🧈'), ('yogurt', '🥛'), ('yoghurt', '🥛'), ('milk', '🥛'),
    ('cream', '🍦'), ('ice cream', '🍨'), ('chocolate', '🍫'), ('candy', '🍬'), ('cookie', '🍪'), ('biscuit', '🍪'),
    ('cake', '🍰'), ('donut', '🍩'), ('doughnut', '🍩'), ('pie', '🥧'), ('honey', '🍯'), ('jam', '🍓'),
    ('apple', '🍎'), ('banana', '🍌'), ('orange', '🍊'), ('lemon', '🍋'), ('lime', '🍋'), ('mango', '🥭'),
    ('pineapple', '🍍'), ('grape', '🍇'), ('strawberr', '🍓'), ('blueberr', '🫐'), ('cherry', '🍒'), ('peach', '🍑'),
    ('pear', '🍐'), ('watermelon', '🍉'), ('melon', '🍈'), ('kiwi', '🥝'), ('coconut', '🥥'), ('avocado', '🥑'),
    ('tomato', '🍅'), ('sweet potato', '🍠'), ('potato', '🥔'), ('carrot', '🥕'), ('corn', '🌽'), ('broccoli', '🥦'),
    ('cucumber', '🥒'), ('lettuce', '🥬'), ('spinach', '🥬'), ('cabbage', '🥬'), ('pepper', '🫑'), ('chili', '🌶️'),
    ('onion', '🧅'), ('garlic', '🧄'), ('mushroom', '🍄'), ('eggplant', '🍆'), ('olive', '🫒'), ('bean', '🫘'),
    ('lentil', '🫘'), ('chickpea', '🫘'), ('peanut', '🥜'), ('almond', '🥜'), ('walnut', '🥜'), ('cashew', '🥜'),
    ('nut', '🥜'), ('oat', '🥣'), ('cereal', '🥣'), ('granola', '🥣'), ('muesli', '🥣'), ('flour', '🌾'),
    ('wheat', '🌾'), ('tofu', '🧆'), ('falafel', '🧆'), ('paneer', '🧀'), ('dal', '🫘'), ('roti', '🫓'),
    ('chapati', '🫓'), ('naan', '🫓'), ('tortilla', '🫓'), ('coffee', '☕'), ('tea', '🍵'), ('juice', '🧃'),
    ('smoothie', '🥤'), ('shake', '🥤'), ('soda', '🥤'), ('cola', '🥤'), ('beer', '🍺'), ('wine', '🍷'),
    ('water', '💧'), ('protein', '💪'),
]
DEFAULT = '🍽️'


def emoji_for(name):
    n = (name or '').lower()
    for key, icon in _ICONS:
        if key in n:
            return icon
    return DEFAULT
