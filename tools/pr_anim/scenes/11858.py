# OpenROAD #11858: widening a column widens the table. The hierarchy
# table, loaded in the default narrow panel and then widened: the base
# viewer shares the panel among the columns, so widening the first one
# squeezes the others and pushes the last off the panel.
STEPS = [
    {"recording": False},
    {"wait_for": "text=Windows"},
    {"wait": 3000},
    {"click": "text=Windows"},
    {"click": ".menu-item:has-text('Hierarchy')"},
    {"wait": 300},
    {"click": ".hierarchy-widget button:has-text('Update')"},
    {"wait": 2500},
    {"drag": [1658, 450], "by": [-1000, 0], "steps": 5},
    {"wait": 500},
    {"move": [1800, 600], "steps": 1},
    {"recording": True},
    {"frame": 800},
    {
        "move": ".hierarchy-table-container th >> nth=0",
        "anchor": "right",
        "dx": -1,
        "steps": 16,
    },
    {"frame": 400},
    {
        "drag": ".hierarchy-table-container th >> nth=0",
        "anchor": "right",
        "dx": -1,
        "by": [220, 0],
        "steps": 16,
    },
    {"move": [1800, 600], "steps": 10},
    {"frame": 3000},
]
VIEWPORT = "2000x800"
CLIP = ".ide-pane-right"
WIDTH = 1000
