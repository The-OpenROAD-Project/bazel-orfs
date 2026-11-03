# Shared setup: the Timing panel, widened, its paths loaded.
SETUP = [
    {"recording": False},
    {"wait_for": "text=Windows"},
    {"wait": 3000},
    {"click": "text=Windows"},
    {"click": ".menu-item:has-text('Timing')"},
    {"wait": 300},
    {"drag": [1258, 450], "by": [-700, 0], "steps": 5},
    {"wait": 300},
    {"click": ".timing-widget button:has-text('Update')"},
    {"wait": 3000},
    {"move": [1200, 860], "steps": 1},
    {"recording": True},
]
