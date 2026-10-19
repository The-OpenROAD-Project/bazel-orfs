#!/usr/bin/env python3
"""The bazel-orfs demo video: script.py's scenes, narrated and encoded.

Each sentence is spoken by Piper (offline, a pinned voice) and becomes one
still frame with the sentence burned in as a caption, held for as long as
it is spoken. The narration is spoken first, so "{N}" in the script (the
title's "in N minutes") says how long the video really is. The stills go through ffmpeg's concat demuxer, the voice is
one WAV beside them, and the ffmpeg that imageio-ffmpeg pins encodes both:
nothing is taken from the host.

    video.py --script full|short --format landscape|portrait \
        --voice-onnx F --voice-json F --gui PNG --gcd PNG \
        --out out.mp4 --srt out.srt [--test]

--test keeps the first two sentences, for a test that it encodes.
"""

import argparse
import array
import os
import subprocess
import sys
import tempfile
import wave

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import script as SCRIPT  # noqa: E402

FORMATS = {"landscape": (1920, 1080), "portrait": (1080, 1920)}
FPS = 30
# Silence after each sentence, and after a scene's last one.
GAP = 0.35
SCENE_GAP = 0.6

BG = (13, 17, 23)
FG = (230, 237, 243)
DIM = (139, 148, 158)
ACCENT = (88, 166, 255)
GOOD = (63, 185, 80)
PANEL = (22, 27, 34)


def font(size):
    return ImageFont.load_default(size=size)


def wrap(draw, text, fnt, width):
    """text as lines no wider than `width` pixels."""
    lines, line = [], ""
    for word in text.split():
        candidate = (line + " " + word).strip()
        if line and draw.textlength(candidate, font=fnt) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


class Canvas(object):
    def __init__(self, size, args):
        self.w, self.h = size
        self.args = args
        self.portrait = self.h > self.w
        self.unit = min(self.w, self.h) / 1080.0
        self.n_text = "N Minutes"

    def fmt(self, text):
        return text.replace("{N}", self.n_text)

    def px(self, n):
        return int(round(n * self.unit))

    def new(self):
        img = Image.new("RGB", (self.w, self.h), BG)
        return img, ImageDraw.Draw(img)

    def caption_top(self):
        """Where the caption band starts; pictures stay above it."""
        return self.h - self.px(300 if self.portrait else 210)

    def caption(self, draw, text):
        fnt = font(self.px(44))
        margin = self.px(60)
        lines = wrap(draw, text, fnt, self.w - 2 * margin)
        step = self.px(56)
        top = self.caption_top() + self.px(30)
        draw.rectangle([0, self.caption_top(), self.w, self.h], fill=PANEL)
        for i, line in enumerate(lines):
            x = (self.w - draw.textlength(line, font=fnt)) / 2
            draw.text((x, top + i * step), line, font=fnt, fill=FG)

    def centred(self, draw, y, text, size, fill):
        fnt = font(self.px(size))
        for i, line in enumerate(wrap(draw, text, fnt, self.w - self.px(120))):
            x = (self.w - draw.textlength(line, font=fnt)) / 2
            draw.text((x, y + i * self.px(size * 1.3)), line, font=fnt, fill=fill)

    # One method per scene kind: (img, draw, opts, sentence index).
    def title(self, img, draw, opts, k):
        mid = self.caption_top() / 2
        title = self.fmt(opts.get("title", SCRIPT.TITLE))
        self.centred(draw, mid - self.px(160), title, 72, FG)
        sub = self.fmt(opts.get("sub", ""))
        self.centred(
            draw, mid + self.px(80 if not self.portrait else 160), sub, 40, ACCENT
        )

    def terminal(self, img, draw, opts, k):
        shown = opts["lines"][: opts["show"][min(k, len(opts["show"]) - 1)]]
        margin = self.px(60)
        room = self.px(340) if opts.get("figures") and not self.portrait else margin
        box = [margin, margin, self.w - room, self.caption_top() - margin]
        draw.rounded_rectangle(box, radius=self.px(18), fill=PANEL, outline=DIM)
        fnt = font(self.px(36 if not self.portrait else 34))
        y = box[1] + self.px(40)
        for line in shown:
            if line.startswith(("$", ">")):
                colour = ACCENT
            elif "GUI" in line and "http" in line:
                colour = GOOD
            else:
                colour = FG
            for part in wrap(draw, line, fnt, box[2] - box[0] - self.px(80)):
                draw.text((box[0] + self.px(40), y), part, font=fnt, fill=colour)
                y += self.px(54)
            y += self.px(16)
        if "note" in opts:
            note = font(self.px(32))
            for i, line in enumerate(wrap(draw, opts["note"], note, box[2] - box[0])):
                draw.text(
                    (box[0] + self.px(40), box[3] - self.px(70) + i * self.px(40)),
                    line,
                    font=note,
                    fill=DIM,
                )

    def lanes(self, img, draw, opts, k):
        """Two columns, one per lane; the sentence about a lane lights it."""
        head, body = font(self.px(48)), font(self.px(36))
        n = len(opts["lanes"])
        margin, gap = self.px(70), self.px(50)
        area = self.caption_top() - 2 * margin
        for i, (name, rows) in enumerate(opts["lanes"]):
            if self.portrait:
                h = (area - gap) / n
                box = [
                    margin,
                    margin + i * (h + gap),
                    self.w - margin,
                    margin + i * (h + gap) + h,
                ]
            else:
                w = (self.w - 2 * margin - gap) / n
                box = [
                    margin + i * (w + gap),
                    margin,
                    margin + i * (w + gap) + w,
                    margin + area,
                ]
            lit = opts.get("light", {}).get(k) == i
            draw.rounded_rectangle(
                box,
                radius=self.px(20),
                fill=PANEL,
                outline=ACCENT if lit else DIM,
                width=self.px(6 if lit else 2),
            )
            x, y = box[0] + self.px(40), box[1] + self.px(36)
            draw.text((x, y), name, font=head, fill=ACCENT if lit else FG)
            y += self.px(90)
            for row in rows:
                for part in wrap(draw, row, body, box[2] - box[0] - self.px(80)):
                    draw.text(
                        (x, y),
                        part,
                        font=body,
                        fill=FG if lit or not opts.get("light") else DIM,
                    )
                    y += self.px(48)
                y += self.px(22)

    def system(self, img, draw, opts, k):
        """The laptop and the server it reaches over the VPN. Items sit on a
        grid of (row, column); a phone transposes it."""
        items = {
            "browser": (0, 0, "Browser", "OpenROAD's GUI"),
            "claude": (1, 0, "Claude terminal", ""),
            "proxy": (0, 1, "gui_proxy", "token checked"),
            "agent": (1, 1, "Claude Code", ""),
            "daemon": (0, 2, "odb-debug", "OpenROAD, design loaded"),
            "mcp": (1, 2, "MCP server", "summaries"),
        }
        links = [
            ("browser", "proxy", "VPN"),
            ("claude", "agent", "ssh"),
            ("proxy", "daemon", ""),
            ("agent", "mcp", ""),
            ("mcp", "daemon", ""),
        ]
        top, bottom = self.px(150), self.caption_top() - self.px(60)
        left, right = self.px(60), self.w - self.px(60)
        cols, rows = 3, 2
        if self.portrait:
            along, across = (bottom - top), (right - left)
            bw, bh = across / rows - self.px(60), along / cols - self.px(150)
        else:
            along, across = (right - left), (bottom - top)
            bw, bh = along / cols - self.px(150), across / rows - self.px(120)
        bh = min(bh, self.px(200))

        def centre(r, c):
            if self.portrait:
                return (
                    left + (r + 0.5) * (right - left) / rows,
                    top + (c + 0.5) * (bottom - top) / cols,
                )
            return (
                left + (c + 0.5) * (right - left) / cols,
                top + (r + 0.5) * (bottom - top) / rows,
            )

        def rect(key):
            x, y = centre(*items[key][:2])
            return [x - bw / 2, y - bh / 2, x + bw / 2, y + bh / 2]

        # The two machines around their items.
        groups = [
            (["browser", "claude"], "Laptop"),
            (["proxy", "agent", "daemon", "mcp"], opts.get("server", "Server")),
        ]
        label = font(self.px(34))
        headings = []
        for keys, name in groups:
            rs = [rect(key) for key in keys]
            pad = self.px(28)
            g = [
                min(r[0] for r in rs) - pad,
                min(r[1] for r in rs) - pad - self.px(50),
                max(r[2] for r in rs) + pad,
                max(r[3] for r in rs) + pad,
            ]
            draw.rounded_rectangle(g, radius=self.px(24), outline=DIM, width=self.px(3))
            headings.append(((g[0] + self.px(24), g[1] + self.px(10)), name))
        for a, b, text in links:
            ra, rb = rect(a), rect(b)
            ca = ((ra[0] + ra[2]) / 2, (ra[1] + ra[3]) / 2)
            cb = ((rb[0] + rb[2]) / 2, (rb[1] + rb[3]) / 2)
            if abs(ca[0] - cb[0]) > abs(ca[1] - cb[1]):
                sx = 1 if cb[0] > ca[0] else -1
                p, q = (ca[0] + sx * bw / 2, ca[1]), (cb[0] - sx * bw / 2, cb[1])
            else:
                sy = 1 if cb[1] > ca[1] else -1
                p, q = (ca[0], ca[1] + sy * bh / 2), (cb[0], cb[1] - sy * bh / 2)
            self.arrow(draw, p, q, False)
            if text:
                f = font(self.px(32))
                mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
                if p[0] == q[0]:
                    # Beside a vertical arrow, not on it.
                    at = (mx + self.px(14), my - self.px(18))
                else:
                    at = (mx - draw.textlength(text, font=f) / 2, my - self.px(46))
                draw.text(at, text, font=f, fill=ACCENT)
        # The machines' names over the arrows that cross their borders.
        for (x, y), name in headings:
            w = draw.textlength(name, font=label)
            draw.rectangle(
                [x - self.px(8), y, x + w + self.px(8), y + self.px(42)], fill=BG
            )
            draw.text((x, y), name, font=label, fill=DIM)
        name_f, note_f = font(self.px(38)), font(self.px(26))
        for key, (_, _, name, note) in items.items():
            r = rect(key)
            draw.rounded_rectangle(r, radius=self.px(16), fill=PANEL, outline=ACCENT)
            for text, f, colour, dy in (
                (name, name_f, FG, 0.28 if note else 0.4),
                (note, note_f, DIM, 0.62),
            ):
                if text:
                    tx = (r[0] + r[2] - draw.textlength(text, font=f)) / 2
                    draw.text(
                        (tx, r[1] + (r[3] - r[1]) * dy), text, font=f, fill=colour
                    )

    def arrow(self, draw, a, b, backwards):
        draw.line([a, b], fill=DIM, width=self.px(6))
        tip, tail = (a, b) if backwards else (b, a)
        dx, dy = tip[0] - tail[0], tip[1] - tail[1]
        n = max((dx * dx + dy * dy) ** 0.5, 1)
        ux, uy, s = dx / n, dy / n, self.px(22)
        draw.polygon(
            [
                tip,
                (tip[0] - ux * s - uy * s * 0.6, tip[1] - uy * s + ux * s * 0.6),
                (tip[0] - ux * s + uy * s * 0.6, tip[1] - uy * s - ux * s * 0.6),
            ],
            fill=DIM,
        )

    def image(self, img, draw, opts, k):
        pic = Image.open(getattr(self.args, opts["image"])).convert("RGB")
        # A wide screenshot on a phone: its layout panel, not the whole page.
        if self.portrait and "portrait_crop" in opts:
            l, t, r, b = opts["portrait_crop"]
            pic = pic.crop(
                (l * pic.width, t * pic.height, r * pic.width, b * pic.height)
            )
        top = self.px(110)
        box_w, box_h = self.w - self.px(80), self.caption_top() - top - self.px(30)
        scale = min(box_w / float(pic.width), box_h / float(pic.height))
        pic = pic.resize(
            (int(pic.width * scale), int(pic.height * scale)), Image.LANCZOS
        )
        y = top + (box_h - pic.height) // 2
        img.paste(pic, (int((self.w - pic.width) / 2), y))
        self.centred(draw, self.px(30), opts["label"], 40, ACCENT)

    def bullets(self, img, draw, opts, k):
        fnt = font(self.px(46))
        y = self.px(100)
        if "heading" in opts:
            self.centred(draw, self.px(50), opts["heading"], 52, ACCENT)
            y = self.px(200)
        show = opts.get("show", [len(opts["items"])])
        for item in opts["items"][: show[min(k, len(show) - 1)]]:
            for j, line in enumerate(wrap(draw, item, fnt, self.w - self.px(260))):
                if j == 0:
                    draw.ellipse(
                        [self.px(90), y + self.px(14), self.px(118), y + self.px(42)],
                        fill=ACCENT,
                    )
                draw.text((self.px(150), y), line, font=fnt, fill=FG)
                y += self.px(62)
            y += self.px(40)

    def box(self, draw, r, outline=ACCENT, fill=PANEL, width=2):
        draw.rounded_rectangle(
            r, radius=self.px(16), fill=fill, outline=outline, width=self.px(width)
        )

    def text_in(self, draw, r, text, size, fill=FG):
        """`text` centred in rectangle `r`, wrapped to fit."""
        fnt = font(self.px(size))
        lines = wrap(draw, text, fnt, r[2] - r[0] - self.px(24))
        step = self.px(size * 1.25)
        y = (r[1] + r[3]) / 2 - step * len(lines) / 2
        for line in lines:
            x = (r[0] + r[2] - draw.textlength(line, font=fnt)) / 2
            draw.text((x, y), line, font=fnt, fill=fill)
            y += step

    def trunk(self, img, draw, opts, k):
        """The chores: a packing list that grows, then one line strikes it."""
        fnt = font(self.px(44))
        y = self.px(90)
        shown = opts["items"][: opts["show"][min(k, len(opts["show"]) - 1)]]
        struck = opts.get("struck", False)
        for item in shown:
            for line in wrap(draw, "- " + item, fnt, self.w - self.px(240)):
                draw.text((self.px(110), y), line, font=fnt, fill=DIM if struck else FG)
                if struck:
                    w = draw.textlength(line, font=fnt)
                    draw.line(
                        [
                            (self.px(110), y + self.px(26)),
                            (self.px(110) + w, y + self.px(26)),
                        ],
                        fill=ACCENT,
                        width=self.px(5),
                    )
                y += self.px(62)
        if struck:
            y += self.px(40)
            self.centred(draw, y, opts.get("answer", ""), 64, GOOD)

    def voyage(self, img, draw, opts, k):
        """The voyage map: routes leaving "you are here"; a legend says a
        solid track is hermetic and a dashed one dirty."""
        routes = opts["routes"]
        cx, cy = self.w / 2, self.caption_top() * (0.5 if not self.portrait else 0.45)
        rx = self.w * (0.36 if not self.portrait else 0.36)
        ry = self.caption_top() * (0.34 if not self.portrait else 0.32)
        lit = opts.get("lit")
        import math

        hub = [cx - self.px(190), cy - self.px(55), cx + self.px(190), cy + self.px(55)]
        for i, name in enumerate(routes):
            a = -math.pi / 2 + 2 * math.pi * i / len(routes)
            x, y = cx + rx * math.cos(a), cy + ry * math.sin(a)
            on = lit is None or i in lit
            colour = ACCENT if on else DIM
            # Each route has both lanes: a solid track beside a dashed one.
            dx, dy = -math.sin(a) * self.px(7), math.cos(a) * self.px(7)
            draw.line(
                [(cx + dx, cy + dy), (x + dx, y + dy)], fill=colour, width=self.px(5)
            )
            steps = 14
            for j in range(0, steps, 2):
                p0 = (cx - dx + (x - cx) * j / steps, cy - dy + (y - cy) * j / steps)
                p1 = (
                    cx - dx + (x - cx) * (j + 1) / steps,
                    cy - dy + (y - cy) * (j + 1) / steps,
                )
                draw.line([p0, p1], fill=colour, width=self.px(5))
            r = [x - self.px(150), y - self.px(42), x + self.px(150), y + self.px(42)]
            self.box(draw, r, outline=colour, width=4 if on else 2)
            self.text_in(draw, r, name, 34, FG if on else DIM)
        self.box(draw, hub, outline=GOOD, width=5)
        self.text_in(draw, hub, opts.get("hub", "You are here"), 36)
        at = opts.get("fogg", "hub")
        if at is not None:
            fh = self.px(150)
            if at == "hub":
                fx, ff = hub[0] - self.px(70), hub[3]
            else:
                a = -math.pi / 2 + 2 * math.pi * at / len(routes)
                x, y = cx + rx * math.cos(a), cy + ry * math.sin(a)
                fx = x + (self.px(200) if math.cos(a) >= -0.01 else -self.px(200))
                ff = y + self.px(42)
            self.figure(
                draw, "fogg", fx, ff, fh, opts.get("pose", "stand"), label=False
            )
        legend = font(self.px(30))
        lx, ly = self.px(60), self.caption_top() - self.px(90)
        draw.line([(lx, ly), (lx + self.px(70), ly)], fill=FG, width=self.px(5))
        draw.text(
            (lx + self.px(90), ly - self.px(18)),
            "hermetic: solved problems",
            font=legend,
            fill=FG,
        )
        ly += self.px(46)
        for j in range(0, 70, 20):
            draw.line(
                [(lx + self.px(j), ly), (lx + self.px(j + 10), ly)],
                fill=FG,
                width=self.px(5),
            )
        draw.text(
            (lx + self.px(90), ly - self.px(18)),
            "dirty: unsolved problems",
            font=legend,
            fill=FG,
        )

    def stages(self, img, draw, opts, k):
        """The flow's stages in a row; each sentence sets their states."""
        names = opts["stages"]
        states = opts["states"][min(k, len(opts["states"]) - 1)]
        n = len(names)
        if self.portrait:
            bw, bh = self.w - self.px(360), self.px(110)
            xs = [self.px(80)] * n
            ys = [self.px(80) + i * self.px(150) for i in range(n)]
        else:
            gap = self.px(30)
            bw = (self.w - self.px(120) - gap * (n - 1)) / n
            bh = self.px(130)
            xs = [self.px(60) + i * (bw + gap) for i in range(n)]
            ys = [self.caption_top() / 2 - bh] * n
        colours = {"cached": GOOD, "rerun": ACCENT, "": DIM}
        label = font(self.px(28))
        for i, name in enumerate(names):
            r = [xs[i], ys[i], xs[i] + bw, ys[i] + bh]
            st = states[i]
            self.box(draw, r, outline=colours[st], width=5 if st else 2)
            self.text_in(draw, r, name, 34)
            if st:
                text = "cached" if st == "cached" else "re-run"
                if self.portrait:
                    at = (r[2] + self.px(20), (r[1] + r[3]) / 2 - self.px(16))
                else:
                    at = (
                        (r[0] + r[2] - draw.textlength(text, font=label)) / 2,
                        r[3] + self.px(16),
                    )
                draw.text(at, text, font=label, fill=colours[st])
        if "note" in opts:
            self.centred(draw, self.caption_top() - self.px(110), opts["note"], 36, DIM)

    def table(self, img, draw, opts, k):
        rows = [opts["header"]] + opts["rows"]
        cols = len(opts["header"])
        top = self.px(140)
        if "heading" in opts:
            self.centred(draw, self.px(50), opts["heading"], 48, ACCENT)
        width = self.w - self.px(160)
        cw = width / cols
        fnt = font(self.px(36 if not self.portrait else 32))
        for i, row in enumerate(rows):
            y = top + i * self.px(76)
            if i == 0:
                draw.line(
                    [
                        (self.px(80), y + self.px(60)),
                        (self.px(80) + width, y + self.px(60)),
                    ],
                    fill=DIM,
                    width=self.px(2),
                )
            for j, cell in enumerate(row):
                draw.text(
                    (self.px(80) + j * cw, y),
                    cell,
                    font=fnt,
                    fill=ACCENT if i == 0 else FG,
                )

    def qa(self, img, draw, opts, k):
        """An audience question in a speech bubble, the role above it, and
        optionally what the answer shows."""
        role, q = opts["role"], opts["question"]
        fnt = font(self.px(44))
        # The asker stands at the left, under the bubble's tail.
        x0 = self.px(80) if self.portrait else self.px(330)
        self.figure(
            draw,
            opts["who"],
            self.px(170),
            self.caption_top() - self.px(55),
            self.px(280 if not self.portrait else 230),
            "ask",
        )
        lines = wrap(draw, q, fnt, self.w - x0 - self.px(240))
        top = self.px(60)
        h = self.px(120) + len(lines) * self.px(56)
        r = [x0, top, self.w - self.px(80), top + h]
        self.box(draw, r, outline=ACCENT, width=4)
        tail = [
            (r[0] + self.px(30), r[3] - self.px(2)),
            (r[0] + self.px(90), r[3] - self.px(2)),
            (r[0] - self.px(40), r[3] + self.px(60)),
        ]
        draw.polygon(tail, fill=PANEL)
        draw.line([tail[0], tail[2], tail[1]], fill=ACCENT, width=self.px(4))
        draw.text(
            (r[0] + self.px(40), r[1] + self.px(24)),
            role,
            font=font(self.px(34)),
            fill=ACCENT,
        )
        for i, line in enumerate(lines):
            draw.text(
                (r[0] + self.px(40), r[1] + self.px(84) + i * self.px(56)),
                line,
                font=fnt,
                fill=FG,
            )
        if "lines" in opts:
            code = font(self.px(32))
            y = r[3] + self.px(100)
            box = [
                x0,
                y - self.px(30),
                self.w - self.px(80),
                self.caption_top() - self.px(40),
            ]
            self.box(draw, box, outline=DIM)
            for line in opts["lines"]:
                for part in wrap(draw, line, code, box[2] - box[0] - self.px(60)) or [
                    ""
                ]:
                    draw.text((box[0] + self.px(30), y), part, font=code, fill=FG)
                    y += self.px(44)

    def mapping(self, img, draw, opts, k):
        """config.mk on the left, what bazel-orfs makes of it on the right."""
        self.centred(draw, self.px(40), opts["heading"], 46, ACCENT)
        rows = opts["rows"]
        fnt = font(self.px(36 if not self.portrait else 30))
        top = self.px(150)
        if self.portrait:
            for i, (a, b) in enumerate(rows):
                y = top + i * self.px(230)
                ra = [self.px(60), y, self.w - self.px(60), y + self.px(80)]
                rb = [
                    self.px(160),
                    y + self.px(130),
                    self.w - self.px(60),
                    y + self.px(200),
                ]
                self.box(draw, ra, outline=DIM)
                self.text_in(draw, ra, a, 30)
                self.arrow(
                    draw,
                    (self.px(100), ra[3]),
                    (self.px(100), rb[1] + self.px(30)),
                    False,
                )
                self.box(draw, rb)
                self.text_in(draw, rb, b, 30)
            return
        lw = self.w * 0.44
        for i, (a, b) in enumerate(rows):
            y = top + i * self.px(150)
            ra = [self.px(60), y, self.px(60) + lw, y + self.px(110)]
            rb = [
                self.w - self.px(60) - lw * 0.85,
                y,
                self.w - self.px(60),
                y + self.px(110),
            ]
            self.box(draw, ra, outline=DIM)
            self.text_in(draw, ra, a, 32)
            self.arrow(
                draw,
                (ra[2] + self.px(10), y + self.px(55)),
                (rb[0] - self.px(10), y + self.px(55)),
                False,
            )
            self.box(draw, rb)
            self.text_in(draw, rb, b, 32)

    def tree(self, img, draw, opts, k):
        """fork: the shared stages once, the trials below them."""
        self.centred(draw, self.px(40), opts["heading"], 46, ACCENT)
        root = opts["root"]
        leaves = opts["leaves"]
        top = self.px(170)
        rw = self.w * 0.5
        r = [(self.w - rw) / 2, top, (self.w + rw) / 2, top + self.px(120)]
        self.box(draw, r, outline=GOOD, width=5)
        self.text_in(draw, r, root, 36)
        n = len(leaves)
        bottom = self.caption_top() - self.px(80)
        lw = (self.w - self.px(120) - self.px(30) * (n - 1)) / n
        for i, leaf in enumerate(leaves):
            x = self.px(60) + i * (lw + self.px(30))
            rl = [x, bottom - self.px(110), x + lw, bottom]
            self.arrow(
                draw, ((r[0] + r[2]) / 2, r[3]), ((rl[0] + rl[2]) / 2, rl[1]), False
            )
            self.box(draw, rl)
            self.text_in(draw, rl, leaf, 30)

    def fix(self, img, draw, opts, k):
        """Inspector Fix: a review comment under his magnifying glass."""
        r = [
            self.px(80),
            self.px(120),
            self.w - self.px(80),
            self.px(120) + self.px(300),
        ]
        self.box(draw, r, outline=DIM)
        draw.text(
            (r[0] + self.px(30), r[1] + self.px(24)),
            opts["who"],
            font=font(self.px(32)),
            fill=DIM,
        )
        fnt = font(self.px(38))
        for i, line in enumerate(
            wrap(draw, opts["claim"], fnt, r[2] - r[0] - self.px(60))
        ):
            draw.text(
                (r[0] + self.px(30), r[1] + self.px(84) + i * self.px(50)),
                line,
                font=fnt,
                fill=FG,
            )
        # Fix himself, below the comment, peering up at it.
        self.figure(
            draw,
            "fix",
            self.w - self.px(260),
            self.caption_top() - self.px(55),
            self.px(300),
            "peer",
        )
        verdicts = opts["verdicts"][: k + 1]
        y = r[3] + self.px(120)
        f = font(self.px(44))
        for v in verdicts:
            draw.text((self.px(120), y), v, font=f, fill=GOOD)
            y += self.px(70)

    # ---- stick figures --------------------------------------------------

    def figure(self, draw, who, x, feet, height, pose="stand", label=True):
        """A stick figure with its character's prop, feet at (x, feet)."""
        s = height
        hr = s * 0.09
        top = feet - s
        hx, hy = x, top + hr
        neck = top + 2 * hr
        hip = feet - s * 0.42
        sh = neck + s * 0.06
        w = max(2, int(s * 0.025))
        line = lambda pts, c=FG: draw.line(pts, fill=c, width=w)  # noqa: E731
        if who == "dan":
            pose = "cross"
        if who == "sam":
            # The backpack behind the body.
            draw.rounded_rectangle(
                [x - s * 0.17, sh, x - s * 0.04, sh + s * 0.24],
                radius=int(s * 0.03),
                outline=ACCENT,
                width=w,
            )
        draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], outline=FG, width=w)
        line([(x, neck), (x, hip)])
        line([(x, hip), (x - s * 0.12, feet)])
        line([(x, hip), (x + s * 0.12, feet)])
        left = (x - s * 0.16, sh + s * 0.25)
        right = {
            "stand": (x + s * 0.16, sh + s * 0.25),
            "ask": (x + s * 0.2, sh - s * 0.2),
            "wave": (x + s * 0.2, sh - s * 0.2),
            "tip": (x + s * 0.07, top + s * 0.02),
            "watch": (x + s * 0.22, sh + s * 0.07),
            "carry": (x + s * 0.18, sh + s * 0.3),
            "point": (x + s * 0.32, sh),
            "peer": (x + s * 0.24, sh - s * 0.06),
        }.get(pose, (x + s * 0.16, sh + s * 0.25))
        if pose == "cross":
            line([(x - s * 0.14, sh + s * 0.04), (x + s * 0.13, sh + s * 0.14)])
            line([(x + s * 0.14, sh + s * 0.04), (x - s * 0.13, sh + s * 0.14)])
        else:
            line([(x, sh), left])
            line([(x, sh), right])
        self.prop(
            draw, who, pose, x, s, hr, hx, hy, top, neck, sh, feet, left, right, w
        )
        if label:
            name = dict(SCRIPT.PEOPLE).get(who, who)
            f = font(max(12, int(s * 0.085)))
            draw.text(
                (x - draw.textlength(name, font=f) / 2, feet + s * 0.03),
                name,
                font=f,
                fill=DIM,
            )

    def prop(
        self, draw, who, pose, x, s, hr, hx, hy, top, neck, sh, feet, left, right, w
    ):
        a = ACCENT
        if who == "fogg":
            # A top hat, tipped when he tips it.
            lift = s * 0.05 if pose == "tip" else 0
            draw.rectangle(
                [
                    hx - hr * 0.8,
                    top - hr * 1.5 - lift,
                    hx + hr * 0.8,
                    top + hr * 0.15 - lift,
                ],
                fill=a,
            )
            draw.line(
                [
                    (hx - hr * 1.3, top + hr * 0.15 - lift),
                    (hx + hr * 1.3, top + hr * 0.15 - lift),
                ],
                fill=a,
                width=w,
            )
            if pose == "watch":
                r = s * 0.035
                draw.ellipse(
                    [right[0] - r, right[1] - r, right[0] + r, right[1] + r],
                    outline=a,
                    width=w,
                )
        elif who == "passepartout":
            t = s * 0.04
            draw.polygon(
                [
                    (x, neck + t * 0.2),
                    (x - t * 1.4, neck - t * 0.6),
                    (x - t * 1.4, neck + t),
                ],
                fill=a,
            )
            draw.polygon(
                [
                    (x, neck + t * 0.2),
                    (x + t * 1.4, neck - t * 0.6),
                    (x + t * 1.4, neck + t),
                ],
                fill=a,
            )
            if pose == "carry":
                draw.rectangle(
                    [
                        right[0] - s * 0.04,
                        right[1],
                        right[0] + s * 0.22,
                        right[1] + s * 0.15,
                    ],
                    outline=a,
                    width=w,
                )
                draw.line(
                    [(right[0] + s * 0.05, right[1]), (right[0] + s * 0.13, right[1])],
                    fill=a,
                    width=w,
                )
            if pose == "point":
                # Handing over the link: a small card.
                draw.rectangle(
                    [
                        right[0],
                        right[1] - s * 0.05,
                        right[0] + s * 0.12,
                        right[1] + s * 0.03,
                    ],
                    outline=GOOD,
                    width=w,
                )
        elif who == "fix":
            draw.arc(
                [hx - hr * 1.15, hy - hr * 1.3, hx + hr * 1.15, hy + hr * 0.6],
                180,
                360,
                fill=a,
                width=w * 2,
            )
            draw.line(
                [(hx - hr * 1.8, hy - hr * 0.3), (hx + hr * 1.8, hy - hr * 0.3)],
                fill=a,
                width=w,
            )
            gx, gy = (
                (right[0] + s * 0.06, right[1] - s * 0.06)
                if pose == "peer"
                else (right[0], right[1] + s * 0.06)
            )
            r = s * 0.07
            draw.ellipse([gx - r, gy - r, gx + r, gy + r], outline=a, width=w)
            draw.line([right, (gx - r * 0.7, gy + r * 0.7)], fill=a, width=w)
        elif who == "maya":
            draw.chord(
                [hx - hr * 1.15, hy - hr * 1.4, hx + hr * 1.15, hy + hr * 0.4],
                180,
                360,
                fill=a,
            )
            draw.line(
                [(hx - hr * 1.5, hy - hr * 0.5), (hx + hr * 1.5, hy - hr * 0.5)],
                fill=a,
                width=w,
            )
        elif who == "arthur":
            draw.line(
                [
                    (left[0] - s * 0.05, left[1] + s * 0.06),
                    (left[0] + s * 0.06, left[1] - s * 0.1),
                ],
                fill=a,
                width=w * 4,
            )
        elif who == "basil":
            b = s * 0.08
            for i in range(3):
                draw.rectangle(
                    [x - s * 0.36, feet - b * (i + 1), x - s * 0.36 + b, feet - b * i],
                    outline=a,
                    width=w,
                )
        elif who == "otto":
            draw.line(
                [left, (left[0] - s * 0.05, left[1] + s * 0.12)], fill=a, width=w * 2
            )
            r = s * 0.03
            cx, cy = left[0] - s * 0.06, left[1] + s * 0.15
            draw.arc([cx - r, cy - r, cx + r, cy + r], 0, 300, fill=a, width=w)
        elif who == "priya":
            b = s * 0.11
            bx, by = x - s * 0.4, feet - b
            draw.rectangle([bx, by, bx + b, feet], outline=a, width=w)
            draw.line([(bx + b / 2, by), (bx + b / 2, by - b * 0.4)], fill=a, width=w)
            for ex in (0.3, 0.7):
                draw.ellipse(
                    [
                        bx + b * ex - 2,
                        by + b * 0.35 - 2,
                        bx + b * ex + 2,
                        by + b * 0.35 + 2,
                    ],
                    fill=a,
                )
        elif who == "rita":
            d = s * 0.06
            for i in range(2):
                dx = left[0] - s * 0.08 + i * d * 1.3
                draw.rectangle([dx, left[1], dx + d, left[1] + d], outline=a, width=w)
        elif who == "tara":
            c = s * 0.08
            cx, cy = left[0] - c / 2, left[1]
            draw.rectangle([cx, cy, cx + c, cy + c], outline=a, width=w)
            for t in (0.25, 0.5, 0.75):
                draw.line(
                    [(cx - c * 0.2, cy + c * t), (cx, cy + c * t)], fill=a, width=1
                )
                draw.line(
                    [(cx + c, cy + c * t), (cx + c * 1.2, cy + c * t)], fill=a, width=1
                )

    def figures(self, draw, opts, k):
        """The figures a scene asks for, at named places, for sentence k."""
        figs = opts.get("figures")
        if isinstance(figs, dict):
            figs = figs.get(k, figs.get("all", []))
        h = self.px(280 if not self.portrait else 230)
        feet = self.caption_top() - self.px(55)
        spots = {
            "right": self.w - self.px(170),
            "left": self.px(170),
            "right2": self.w - self.px(380),
            "centre": self.w / 2,
        }
        for who, spot, pose in figs or []:
            self.figure(draw, who, spots[spot], feet, h, pose)

    def cast(self, img, draw, opts, k):
        """Who is who: the figures in a row (two on a phone), named."""
        self.centred(draw, self.px(50), opts["heading"], 56, ACCENT)
        who = opts["cast"]
        # Up to five abreast, so the names fit under them.
        per_row = len(who) if len(who) <= 5 else (len(who) + 1) // 2
        rows = [who[i : i + per_row] for i in range(0, len(who), per_row)]
        h = self.px(300 if len(who) <= 3 else 230)
        area_top = self.px(170)
        step = (self.caption_top() - area_top - self.px(40)) / len(rows)
        for r, row in enumerate(rows):
            feet = area_top + step * (r + 1) - self.px(50)
            for i, key in enumerate(row):
                x = self.w * (i + 0.5) / len(row)
                pose = {"fogg": "watch", "passepartout": "carry", "fix": "peer"}.get(
                    key, "stand"
                )
                self.figure(draw, key, x, feet, h, pose)


class Voice(object):
    def __init__(self, onnx, config):
        from piper import PiperVoice

        self.voice = PiperVoice.load(onnx, config_path=config)

    def say(self, text, path):
        """Speak `text` into a WAV at `path`; return (rate, int16 samples)."""
        with wave.open(path, "wb") as w:
            self.voice.synthesize_wav(SCRIPT.say(text), w)
        with wave.open(path, "rb") as r:
            if r.getnchannels() != 1 or r.getsampwidth() != 2:
                raise SystemExit("unexpected voice format in %s" % path)
            samples = array.array("h", r.readframes(r.getnframes()))
            return r.getframerate(), samples


def stamp(seconds):
    ms = int(round(seconds * 1000))
    return "%02d:%02d:%02d,%03d" % (
        ms // 3600000,
        ms // 60000 % 60,
        ms // 1000 % 60,
        ms % 1000,
    )


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--script", choices=sorted(SCRIPT.SCRIPTS), required=True)
    p.add_argument("--format", choices=sorted(FORMATS), required=True)
    p.add_argument("--voice-onnx", required=True)
    p.add_argument("--voice-json", required=True)
    p.add_argument("--gui", required=True)
    p.add_argument("--gcd", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--srt", required=True)
    p.add_argument("--test", action="store_true")
    args = p.parse_args(argv[1:])

    canvas = Canvas(FORMATS[args.format], args)
    voice = Voice(args.voice_onnx, args.voice_json)
    sentences = [
        (kind, opts, k, text)
        for kind, opts, said in SCRIPT.SCRIPTS[args.script]
        for k, text in enumerate(said)
    ]
    if args.test:
        sentences = sentences[:2]

    tmp = tempfile.mkdtemp(prefix="warm_gui_video.")
    spoken = {}

    def speak(text):
        if text not in spoken:
            path = os.path.join(tmp, "s%03d.wav" % len(spoken))
            spoken[text] = voice.say(text, path)
        return spoken[text]

    def length(n_text):
        total = 0.0
        for i, (_, _, k, text) in enumerate(sentences):
            r, samples = speak(text.replace("{N}", n_text))
            last = i + 1 == len(sentences) or sentences[i + 1][2] == 0
            total += len(samples) / float(r) + (SCENE_GAP if last else GAP)
        return total

    def minutes(n):
        return "%d Minute%s" % (n, "" if n == 1 else "s")

    # "{N}" is the video's own length, which depends on how long the
    # sentence that says it takes: settle it.
    n = 1
    for _ in range(4):
        found = max(1, int(round(length(minutes(n)) / 60.0)))
        if found == n:
            break
        n = found
    canvas.n_text = minutes(n)

    audio, rate, t = array.array("h"), None, 0.0
    concat, captions = [], []
    for i, (kind, opts, k, text) in enumerate(sentences):
        text = canvas.fmt(text)
        r, samples = speak(text)
        if rate is None:
            rate = r
        last = i + 1 == len(sentences) or sentences[i + 1][2] == 0
        pad = int(rate * (SCENE_GAP if last else GAP))
        audio.extend(samples)
        audio.extend(array.array("h", [0]) * pad)
        seconds = (len(samples) + pad) / float(rate)
        captions.append((t, t + len(samples) / float(rate), text))
        t += seconds

        img, draw = canvas.new()
        getattr(canvas, kind)(img, draw, opts, k)
        canvas.figures(draw, opts, k)
        canvas.caption(draw, text)
        frame = os.path.join(tmp, "f%03d.png" % i)
        img.save(frame)
        concat.append("file '%s'\nduration %.3f\n" % (frame, seconds))

    # The concat demuxer drops the last entry's duration unless the file
    # is listed once more.
    concat.append("file '%s'\n" % frame)
    listing = os.path.join(tmp, "frames.txt")
    with open(listing, "w") as f:
        f.writelines(concat)
    voice_wav = os.path.join(tmp, "voice.wav")
    with wave.open(voice_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(audio.tobytes())

    subprocess.check_call(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            listing,
            "-i",
            voice_wav,
            "-vf",
            "fps=%d,format=yuv420p" % FPS,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast" if args.test else "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            "-movflags",
            "+faststart",
            args.out,
        ]
    )
    with open(args.srt, "w") as f:
        for n, (a, b, text) in enumerate(captions, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (n, stamp(a), stamp(b), text))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
