#!/usr/bin/env python3
"""The bazel-orfs demo video: script.py's scenes, narrated and encoded.

Each sentence is spoken by Piper (offline, a pinned voice) and becomes one
still frame with the sentence burned in as a caption, held for as long as
it is spoken. A scene marked "animate" draws itself over its first second
instead, and a gauge in the corner slides between the values the scenes
set. The frames go through ffmpeg's concat demuxer, the voice is one WAV
beside them, and the ffmpeg that imageio-ffmpeg pins encodes both:
nothing is taken from the host.

    video.py --script full|short --format landscape|portrait \
        --voice-onnx F --voice-json F --gui PNG \
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
# An animated scene draws itself over its first ANIM seconds, at ANIM_FPS,
# then holds its last frame.
ANIM = 1.2
ANIM_FPS = 15
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
        # Animation progress of the frame being drawn, 0..1.
        self.t = 1.0
        self.gauge_from = None
        self.gauge_to = None

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
        title = opts.get("title", SCRIPT.TITLE)
        self.centred(draw, mid - self.px(160), title, 72, FG)
        sub = opts.get("sub", "")
        self.centred(
            draw, mid + self.px(80 if not self.portrait else 160), sub, 40, ACCENT
        )

    def terminal(self, img, draw, opts, k):
        shown = opts["lines"][: opts["show"][min(k, len(opts["show"]) - 1)]]
        margin = self.px(60)
        room = margin
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

    # ---- the gauge and the animated scenes ------------------------------

    def ease(self):
        return 1 - (1 - self.t) ** 2

    def gauge(self, draw):
        """Minutes until you can decide, per lane, in the top right corner;
        it slides from the previous scene's values to this one's."""
        if not self.gauge_to:
            return
        rows = self.gauge_to
        prev = dict(self.gauge_from or [])
        e = self.ease()
        w, rh = self.px(560), self.px(54)
        x0 = self.w - w - self.px(30)
        y0 = self.px(24)
        h = self.px(60) + rh * len(rows)
        draw.rounded_rectangle(
            [x0, y0, x0 + w, y0 + h],
            radius=self.px(14),
            fill=PANEL,
            outline=DIM,
            width=2,
        )
        draw.text(
            (x0 + self.px(20), y0 + self.px(12)),
            "minutes until you can decide",
            font=font(self.px(26)),
            fill=DIM,
        )
        top = max(6.0, max(v for _, v in rows))
        for i, (lane, v) in enumerate(rows):
            a = prev.get(lane, v)
            val = a + (v - a) * e
            y = y0 + self.px(52) + i * rh
            f = font(self.px(28))
            draw.text((x0 + self.px(20), y), lane, font=f, fill=FG)
            bx0, bx1 = x0 + self.px(180), x0 + w - self.px(110)
            draw.rectangle(
                [bx0, y + self.px(6), bx1, y + self.px(30)], outline=DIM, width=1
            )
            draw.rectangle(
                [
                    bx0,
                    y + self.px(6),
                    bx0 + (bx1 - bx0) * min(val, top) / top,
                    y + self.px(30),
                ],
                fill=ACCENT if lane == "Bazel" else GOOD,
            )
            draw.text((bx1 + self.px(12), y), "%.1f" % val, font=f, fill=FG)

    def landscape(self, img, draw, opts, k):
        """Hills and cliffs, from big drops to a plateau that ends at WNS = 0;
        a walker moves along it."""
        import math

        left, right = self.px(80), self.w - self.px(80)
        top, bottom = self.px(220), self.caption_top() - self.px(120)
        pts = []
        n = 240
        for j in range(n + 1):
            x = j / float(n)
            # Big rough drops early, a gentle plateau late, a cliff at the end.
            y = (
                0.95 * (1 - x) ** 2.2
                + 0.12 * math.sin(14 * x) * (1 - x) ** 1.5
                + 0.06 * abs(math.sin(31 * x)) * (1 - x)
            )
            pts.append(
                (left + x * (right - left) * 0.92, top + (1 - y) * (bottom - top) * 0.8)
            )
        draw.line(pts, fill=FG, width=self.px(4))
        cliff_x = pts[-1][0]
        draw.line([pts[-1], (cliff_x, bottom)], fill=FG, width=self.px(4))
        draw.line([(cliff_x, top), (cliff_x, bottom)], fill=GOOD, width=self.px(2))
        draw.text(
            (cliff_x - self.px(140), top - self.px(50)),
            "WNS = 0",
            font=font(self.px(40)),
            fill=GOOD,
        )
        draw.text(
            (left, top - self.px(50)),
            "easy problems: big drops",
            font=font(self.px(32)),
            fill=DIM,
        )
        draw.text(
            (left + (right - left) * 0.48, top + (bottom - top) * 0.55),
            "a few percent apart",
            font=font(self.px(32)),
            fill=DIM,
        )
        # The walker, a dot, moves along as the sentences go.
        where = opts.get("walk", [0.1, 0.9])[min(k, len(opts.get("walk", [0])) - 1)]
        prev = (
            opts.get("walk", [0.1])[max(0, min(k, len(opts.get("walk", [0])) - 1) - 1)]
            if k
            else 0.0
        )
        pos = prev + (where - prev) * self.ease()
        px, py = pts[min(n, int(pos * n))]
        r = self.px(16)
        draw.ellipse([px - r, py - 2 * r, px + r, py], fill=ACCENT)

    def timeline(self, img, draw, opts, k):
        """Builds on a timeline, each ending in a decision; the last, the
        tapeout build, ends in a chip."""
        n = 9
        left, right = self.px(100), self.w - self.px(160)
        y = self.caption_top() * 0.55
        draw.line([(left, y), (right + self.px(60), y)], fill=DIM, width=self.px(3))
        shown = max(1, int(round(n * self.ease()))) if opts.get("grow") else n
        for j in range(shown):
            x = left + j * (right - left) / (n - 1)
            last = j == n - 1
            draw.rectangle(
                [x - self.px(40), y - self.px(50), x + self.px(40), y],
                outline=FG,
                width=2,
                fill=PANEL,
            )
            if last:
                c = self.px(26)
                draw.rectangle(
                    [x - c, y - self.px(130) - c, x + c, y - self.px(130) + c],
                    outline=GOOD,
                    width=self.px(4),
                )
                for t in range(-2, 3):
                    draw.line(
                        [
                            (x + t * c / 2.5, y - self.px(130) - c - self.px(12)),
                            (x + t * c / 2.5, y - self.px(130) - c),
                        ],
                        fill=GOOD,
                        width=2,
                    )
                draw.text(
                    (x - self.px(60), y + self.px(20)),
                    "tapeout",
                    font=font(self.px(30)),
                    fill=GOOD,
                )
            else:
                draw.text(
                    (x - self.px(8), y - self.px(110)),
                    "?",
                    font=font(self.px(48)),
                    fill=ACCENT,
                )
        draw.text(
            (left, y + self.px(20)),
            "every build before it: data for a decision",
            font=font(self.px(30)),
            fill=DIM,
        )

    def stagebars(self, img, draw, opts, k):
        """The measured stage times as bars that grow in time-lapse; a cut
        after a stage greys out what the decision does not need."""
        bars = opts["bars"]
        cut = opts.get("cut", [None])[min(k, len(opts.get("cut", [None])) - 1)]
        top = self.px(150)
        bottom = self.caption_top() - self.px(120)
        step = (bottom - top) / len(bars)
        bh = min(step * 0.7, self.px(64))
        x0, x1 = self.px(280), self.w - self.px(700 if not self.portrait else 260)
        scale = (x1 - x0) / float(max(v for _, v in bars))
        e = self.ease() if opts.get("grow") and k == 0 else 1.0
        f = font(self.px(34))
        after = False
        total_kept = 0
        for i, (name, v) in enumerate(bars):
            y = top + i * step
            grey = after
            colour = DIM if grey else ACCENT
            draw.text(
                (self.px(60), y + bh / 2 - self.px(20)),
                name,
                font=f,
                fill=DIM if grey else FG,
            )
            draw.rectangle([x0, y, x0 + v * scale * e, y + bh], fill=colour)
            draw.text(
                (x0 + v * scale * e + self.px(14), y + bh / 2 - self.px(20)),
                "%g s" % v,
                font=f,
                fill=colour,
            )
            if not grey:
                total_kept += v
            if name == cut:
                after = True
                yc = y + bh + (step - bh) / 2
                draw.line(
                    [(self.px(40), yc), (x1 + self.px(160), yc)],
                    fill=GOOD,
                    width=self.px(4),
                )
                draw.text(
                    (x1 - self.px(120), yc - self.px(46)),
                    "decide here",
                    font=f,
                    fill=GOOD,
                )
        total = sum(v for _, v in bars)
        note = (
            "%g s to final" % total
            if cut is None
            else "%g s to decide, %g s to final" % (total_kept, total)
        )
        self.centred(draw, bottom + self.px(30), note, 38, GOOD if cut else FG)

    def buildrun(self, img, draw, opts, k):
        """bazelisk build in a sealed box; bazelisk run reaching out."""
        mid = self.w / 2
        top, h = self.px(200), self.px(420)
        lb = [self.px(120), top, mid - self.px(80), top + h]
        rb = [mid + self.px(80), top, self.w - self.px(120), top + h]
        lit = opts.get("light", [0, 1])[min(k, len(opts.get("light", [0])) - 1)]
        for j, (r, title, lines) in enumerate(
            (
                (
                    lb,
                    "bazelisk build",
                    [
                        "sealed off from your machine",
                        "every input recorded",
                        "result remembered",
                    ],
                ),
                (
                    rb,
                    "bazelisk run",
                    [
                        "build, then run the result",
                        "in your terminal and browser",
                        "the dirty lane, the GUI",
                    ],
                ),
            )
        ):
            on = lit in (j, 2)
            draw.rounded_rectangle(
                r,
                radius=self.px(20),
                fill=PANEL,
                outline=ACCENT if on else DIM,
                width=self.px(6 if on else 2),
            )
            draw.text(
                (r[0] + self.px(36), r[1] + self.px(30)),
                title,
                font=font(self.px(48)),
                fill=ACCENT if on else FG,
            )
            for i, line in enumerate(lines):
                draw.text(
                    (r[0] + self.px(36), r[1] + self.px(130) + i * self.px(60)),
                    line,
                    font=font(self.px(34)),
                    fill=FG if on else DIM,
                )
        # The sealed box: a padlock line around the build box.
        draw.rectangle(
            [
                lb[0] - self.px(14),
                lb[1] - self.px(14),
                lb[2] + self.px(14),
                lb[3] + self.px(14),
            ],
            outline=DIM,
            width=self.px(2),
        )
        e = self.ease()
        for dy in (0.3, 0.6):
            y = rb[1] + h * dy
            draw.line(
                [(rb[2], y), (rb[2] + self.px(90) * e, y)], fill=GOOD, width=self.px(5)
            )

    def cards(self, img, draw, opts, k):
        """Results as cards: a new one slides in for a change; switching back
        brings the old one forward without running anything."""
        items = opts["cards"]
        sel = opts["select"][min(k, len(opts["select"]) - 1)]
        cw, ch = self.px(420), self.px(300)
        y = self.px(220)
        gap = (self.w - len(items) * cw) / (len(items) + 1)
        for j, (title, sub) in enumerate(items):
            x = gap + j * (cw + gap)
            on = j == sel
            lift = self.px(40) * self.ease() if on else 0
            r = [x, y - lift, x + cw, y + ch - lift]
            draw.rounded_rectangle(
                r,
                radius=self.px(18),
                fill=PANEL,
                outline=ACCENT if on else DIM,
                width=self.px(6 if on else 2),
            )
            self.text_in(draw, [r[0], r[1], r[2], r[1] + ch * 0.55], title, 40, FG)
            self.text_in(
                draw, [r[0], r[1] + ch * 0.5, r[2], r[3]], sub, 32, GOOD if on else DIM
            )

    def deps(self, img, draw, opts, k):
        """An edited flow script: Bazel lights every stage that reads the
        scripts; the dirty lane lights one substep."""
        stages = ["synth", "floorplan", "place", "cts", "grt", "route", "final"]
        subs = ["3_1 gp_skip_io", "3_2 iop", "3_3 gp", "3_4 resized", "3_5 dp"]
        e = self.ease()
        f = font(self.px(32))
        y1, y2 = self.px(200), self.px(500)
        draw.text(
            (self.px(60), y1 - self.px(70)),
            "bazelisk build: every stage that reads the flow scripts",
            font=f,
            fill=ACCENT,
        )
        bw = (self.w - self.px(120) - self.px(20) * 6) / 7
        lit = int(round(6 * e)) if k == 0 else 6
        for i, s_ in enumerate(stages):
            x = self.px(60) + i * (bw + self.px(20))
            on = 1 <= i <= lit
            draw.rounded_rectangle(
                [x, y1, x + bw, y1 + self.px(90)],
                radius=self.px(12),
                fill=PANEL,
                outline=ACCENT if on else DIM,
                width=self.px(5 if on else 2),
            )
            self.text_in(
                draw, [x, y1, x + bw, y1 + self.px(90)], s_, 30, FG if on else DIM
            )
        draw.text(
            (self.px(60), y2 - self.px(70)),
            "dirty lane: make do-3_3_place_gp",
            font=f,
            fill=GOOD,
        )
        sw = (self.w - self.px(120) - self.px(20) * 4) / 5
        for i, s_ in enumerate(subs):
            x = self.px(60) + i * (sw + self.px(20))
            on = i == 2 and k >= 1
            draw.rounded_rectangle(
                [x, y2, x + sw, y2 + self.px(90)],
                radius=self.px(12),
                fill=PANEL,
                outline=GOOD if on else DIM,
                width=self.px(5 if on else 2),
            )
            self.text_in(
                draw, [x, y2, x + sw, y2 + self.px(90)], s_, 30, FG if on else DIM
            )
        if k >= 1:
            draw.text(
                (self.px(60), y2 + self.px(120)),
                "12 s",
                font=font(self.px(56)),
                fill=GOOD,
            )

    def repair(self, img, draw, opts, k):
        """The shape of a repair_timing run (coralnpu, OpenROAD #11684): most
        of the gain early, a long flat stretch, then a late jump."""
        left, right = self.px(160), self.w - self.px(120)
        top, bottom = self.px(170), self.caption_top() - self.px(140)
        draw.line(
            [(left, top), (left, bottom), (right, bottom)], fill=DIM, width=self.px(3)
        )
        f = font(self.px(28))
        draw.text(
            (left - self.px(120), top - self.px(50)), "WNS gained", font=f, fill=DIM
        )
        draw.text(
            (right - self.px(280), bottom + self.px(16)),
            "repair progress",
            font=f,
            fill=DIM,
        )

        # A shape, not a scale: the RFC gives the proportions (80 % of the
        # main phase's gain in its first 10 % of rows, nothing for the next
        # 42 %) and the last gasp's two values, not the starting WNS.
        def wns(x):
            if x < 0.10:
                return 0.8 * (x / 0.10) ** 0.6
            if x < 0.52:
                return 0.8
            if x < 0.90:
                return 0.8 + 0.2 * ((x - 0.52) / 0.38) ** 2
            return 1.0 + 0.3 * min(1.0, (x - 0.90) / 0.04)

        lo, hi = 0.0, 1.35
        e = self.ease() if k == 0 else 1.0
        n = 200
        pts = []
        for j in range(int(n * e) + 1):
            x = j / float(n)
            v = wns(x)
            pts.append(
                (
                    left + x * (right - left),
                    bottom - (v - lo) / (hi - lo) * (bottom - top),
                )
            )
        if len(pts) > 1:
            draw.line(pts, fill=ACCENT, width=self.px(5))
        if k >= 1:
            xa, xb = left + 0.10 * (right - left), left + 0.52 * (right - left)
            draw.text(
                ((xa + xb) / 2 - self.px(140), top + self.px(40)),
                "nothing for 42 % of the run",
                font=f,
                fill=GOOD,
            )
            draw.text(
                (right - self.px(420), top - self.px(10)),
                "last gasp: -46.6 to -35.0 ps",
                font=f,
                fill=GOOD,
            )
        draw.text(
            (left, bottom + self.px(56)),
            "shape from coralnpu, OpenROAD #11684",
            font=font(self.px(24)),
            fill=DIM,
        )


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

    audio, rate, t = array.array("h"), None, 0.0
    concat, captions = [], []
    for i, (kind, opts, k, text) in enumerate(sentences):
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

        # The gauge: this sentence's values, sliding from the last ones.
        # A scene sets it, keeps it (no "gauge"), or hides it ("hide").
        g = opts.get("gauge", "keep")
        if isinstance(g, dict):
            g = g.get(k, g.get("all", "keep"))
        if g == "keep":
            g = canvas.gauge_to
        elif g == "hide":
            g = None
        canvas.gauge_from, canvas.gauge_to = canvas.gauge_to, g
        moving = canvas.gauge_from != canvas.gauge_to and bool(canvas.gauge_to)
        steps = (
            int(ANIM * ANIM_FPS)
            if (opts.get("animate") or moving) and seconds > ANIM
            else 1
        )
        for j in range(steps):
            canvas.t = (j + 1) / float(steps)
            img, draw = canvas.new()
            getattr(canvas, kind)(img, draw, opts, k)
            canvas.gauge(draw)
            canvas.caption(draw, text)
            frame = os.path.join(tmp, "f%03d_%02d.png" % (i, j))
            img.save(frame)
            held = (
                seconds - (steps - 1) / float(ANIM_FPS)
                if j == steps - 1
                else 1.0 / ANIM_FPS
            )
            concat.append("file '%s'\nduration %.3f\n" % (frame, held))
        canvas.t = 1.0

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
