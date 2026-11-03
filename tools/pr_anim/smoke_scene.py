"""The smoke test's scene: across a column border, then a busy page."""

STEPS = [
    {"wait_for": "#border"},
    {"frame": 200},
    {"move": "#border"},
    {"drag": "#border", "by": [80, 0], "steps": 4},
    {"eval": "document.documentElement.classList.add('busy')"},
    {"move": "#plain", "steps": 3},
    {"frame": 500},
]
