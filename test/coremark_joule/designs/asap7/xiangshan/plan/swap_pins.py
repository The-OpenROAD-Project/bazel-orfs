"""Narrow pin arm: in run 25's pin files, each flush/redirect pin (with a
placement hint) swaps slots with the pin nearest its hint on the block's
logic-facing edge; every other pin keeps its slot."""
import json, re, sys
plan_dir, hints_path, layout_html = sys.argv[1:4]
pat = re.compile(r'(flush|redirect)', re.I)
S = json.loads(re.search(r'const SIX = (\{.*?\});\n', open(layout_html).read()).group(1))
B = {b['name']: b for b in S['blocks']}
hints = {}
for l in open(hints_path):
    t = l.split()
    if len(t) == 5 and t[0] == 'hint':
        hints[(t[1], t[2])] = (float(t[3]), float(t[4]))
row = re.compile(r'^(\s+)(\S+) (M\d) ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)$')
for name, b in B.items():
    path = '%s/%s_pins.tcl' % (plan_dir, name)
    lines = open(path).read().split('\n')
    pins = {}
    for i, l in enumerate(lines):
        m = row.match(l)
        if m:
            pins[m.group(2)] = [i, m.group(1), m.group(3), m.group(4), m.group(5), m.group(6), m.group(7)]
    ys = [float(v[4]) for v in pins.values()]
    edge_y = min(ys) if b['side'] == 'top' else max(ys)  # top row: logic below
    on_edge = [p for p, v in pins.items() if abs(float(v[4]) - edge_y) < 1e-3]
    movers = sorted((hints[(name, p)][0] - b['x'], p) for p in pins
                    if pat.search(p) and (name, p) in hints)
    taken = set()
    swaps = 0
    for want, p in movers:
        free = [q for q in on_edge if q not in taken and not (pat.search(q) and (name, q) in hints and q != p)]
        q = min(free, key=lambda q: abs(float(pins[q][3]) - want))
        taken.add(q)
        if q == p:
            continue
        # swap slots (layer and geometry go with the slot)
        for k in (2, 3, 4, 5, 6):
            pins[p][k], pins[q][k] = pins[q][k], pins[p][k]
        swaps += 1
    for p, v in pins.items():
        lines[v[0]] = '%s%s %s %s %s %s %s' % (v[1], p, v[2], v[3], v[4], v[5], v[6])
    open(path, 'w').write('\n'.join(lines))
    print('%-16s broadcast pins %4d, swaps %4d' % (name, len(movers), swaps))
