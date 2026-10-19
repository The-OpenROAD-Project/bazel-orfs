#!/usr/bin/env python3
"""The bazel-orfs demo video: script.py's scenes, narrated and encoded.

Each sentence is spoken by Piper (offline, a pinned voice) and becomes one
still frame with the sentence burned in as a caption, held for as long as
it is spoken. A scene marked "animate" draws itself over its first second
instead. The frames go through ffmpeg's concat demuxer, the voice is one WAV
beside them, and the ffmpeg that imageio-ffmpeg pins encodes both:
nothing is taken from the host.

    video.py --script full|short --format landscape|portrait \
        --voice-onnx F --voice-json F \
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
# Slow enough to follow: a second after each sentence, longer after a
# scene, and the voice a quarter slower than Piper's default.
GAP = 1.0
SCENE_GAP = 2.5
LENGTH_SCALE = 1.25

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
        # Room at the top for the headline, when a scene has one.
        self.head = 0

    def px(self, n):
        return int(round(n * self.unit))

    def new(self):
        img = Image.new("RGB", (self.w, self.h), BG)
        return img, ImageDraw.Draw(img)

    def caption_top(self):
        """The bottom of the picture: the spoken sentences go in the .srt,
        not on screen, so only a margin is left."""
        return self.h - self.px(60)

    def headline(self, draw, opts, k):
        """The one thing to read: a few words in large type at the top.
        Scenes leave self.head of room for it."""
        text = opts.get("headline")
        if isinstance(text, dict):
            text = text.get(k, text.get("all"))
        if text:
            self.centred(draw, self.px(50), text, 76, FG)

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
        lines_h = (
            self.px(50)
            + len(opts["lines"]) * self.px(96)
            + (self.px(80) if "note" in opts else 0)
        )
        box = [
            margin,
            margin + self.head,
            self.w - room,
            min(self.caption_top() - margin, margin + self.head + lines_h),
        ]
        draw.rounded_rectangle(box, radius=self.px(18), fill=PANEL, outline=DIM)
        fnt = font(self.px(52 if not self.portrait else 34))
        y = box[1] + self.px(50)
        for line in shown:
            if line.startswith(("$", ">")):
                colour = ACCENT
            elif "GUI" in line and "http" in line:
                colour = GOOD
            else:
                colour = FG
            for part in wrap(draw, line, fnt, box[2] - box[0] - self.px(80)):
                draw.text((box[0] + self.px(40), y), part, font=fnt, fill=colour)
                y += self.px(78)
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

    # ---- the animated scenes --------------------------------------------

    def ease(self):
        return 1 - (1 - self.t) ** 2

    def timeline(self, img, draw, opts, k):
        """Builds on a timeline, each ending in a decision; the last, the
        tapeout build, ends in a chip."""
        n = 9
        left, right = self.px(100), self.w - self.px(220)
        y = self.caption_top() * 0.55
        draw.line(
            [(left, y), (right + self.px(1.6 * 60), y)],
            fill=DIM,
            width=self.px(1.6 * 3),
        )
        shown = max(1, int(round(n * self.ease()))) if opts.get("grow") else n
        for j in range(shown):
            x = left + j * (right - left) / (n - 1)
            last = j == n - 1
            draw.rectangle(
                [
                    x - self.px(1.6 * 40),
                    y - self.px(1.6 * 50),
                    x + self.px(1.6 * 40),
                    y,
                ],
                outline=FG,
                width=2,
                fill=PANEL,
            )
            if last:
                c = self.px(1.6 * 26)
                draw.rectangle(
                    [
                        x - c,
                        y - self.px(1.6 * 130) - c,
                        x + c,
                        y - self.px(1.6 * 130) + c,
                    ],
                    outline=GOOD,
                    width=self.px(1.6 * 4),
                )
                for t in range(-2, 3):
                    draw.line(
                        [
                            (
                                x + t * c / 2.5,
                                y - self.px(1.6 * 130) - c - self.px(1.6 * 12),
                            ),
                            (x + t * c / 2.5, y - self.px(1.6 * 130) - c),
                        ],
                        fill=GOOD,
                        width=2,
                    )
                draw.text(
                    (x - self.px(1.6 * 60), y + self.px(1.6 * 20)),
                    "tapeout",
                    font=font(self.px(1.6 * 30)),
                    fill=GOOD,
                )
            elif opts.get("answers") and k >= 1 and j < (n - 1) * self.ease():
                # A tick: the question answered.
                cx, cy = x, y - self.px(1.6 * 90)
                draw.line(
                    [
                        (cx - self.px(1.6 * 18), cy),
                        (cx - self.px(1.6 * 4), cy + self.px(1.6 * 16)),
                        (cx + self.px(1.6 * 22), cy - self.px(1.6 * 20)),
                    ],
                    fill=GOOD,
                    width=self.px(1.6 * 6),
                )
            else:
                draw.text(
                    (x - self.px(1.6 * 8), y - self.px(1.6 * 110)),
                    "?",
                    font=font(self.px(1.6 * 48)),
                    fill=ACCENT,
                )
        draw.text(
            (left, y + self.px(1.6 * 20)),
            "every build before it answers a question",
            font=font(self.px(1.6 * 30)),
            fill=DIM,
        )

    def memory(self, img, draw, opts, k):
        """The ORFS stages; under each, its saved result and the exact
        inputs that made it. Then the same inputs come again, and the saved
        result comes back."""
        names = ["synth", "floorplan", "place", "cts", "grt", "route", "final"]
        n = len(names)
        e = self.ease()
        top = self.px(170) + self.head
        if self.portrait:
            bw, bh, gap = self.w - self.px(520), self.px(84), self.px(30)
            xs = [self.px(60)] * n
            ys = [top + i * (bh + gap) for i in range(n)]
            rx = lambda i: xs[i] + bw + self.px(40)  # noqa: E731
            ry = lambda i: ys[i]  # noqa: E731
            rw, rh = self.w - rx(0) - self.px(40), bh
        else:
            gap = self.px(24)
            bw = (self.w - self.px(120) - gap * (n - 1)) / n
            bh = self.px(120)
            xs = [self.px(60) + i * (bw + gap) for i in range(n)]
            ys = [top] * n
            rx = lambda i: xs[i]  # noqa: E731
            ry = lambda i: ys[i] + bh + self.px(110)  # noqa: E731
            rw, rh = bw, self.px(320)
        shown = n if k else max(1, int(round(n * e)))
        for i in range(shown):
            self.box(
                draw, [xs[i], ys[i], xs[i] + bw, ys[i] + bh], outline=ACCENT, width=3
            )
            self.text_in(draw, [xs[i], ys[i], xs[i] + bw, ys[i] + bh], names[i], 40)
            if i + 1 < n and not self.portrait:
                self.arrow(
                    draw,
                    (xs[i] + bw, ys[i] + bh / 2),
                    (xs[i + 1], ys[i] + bh / 2),
                    False,
                )
        if k >= 1:
            # Each saved result, with the exact inputs that made it.
            cards = n if k >= 2 else max(1, int(round(n * e)))
            for i in range(cards):
                r = [rx(i), ry(i), rx(i) + rw, ry(i) + rh]
                hit = k >= 2 and i == opts.get("hit", 2)
                self.box(draw, r, outline=GOOD if hit else DIM, width=6 if hit else 2)
                f = font(self.px(32))
                lines = [
                    "result",
                    "made from:",
                    "RTL, SDC",
                    "settings",
                    "tool versions",
                ]
                if self.portrait:
                    lines = ["result, made from: RTL, SDC, settings, tools"]
                for j, line in enumerate(lines):
                    draw.text(
                        (r[0] + self.px(18), r[1] + self.px(20) + j * self.px(56)),
                        line,
                        font=f,
                        fill=GOOD if (hit or j == 0) else DIM,
                    )
        if k >= 2:
            self.centred(
                draw,
                self.caption_top() - self.px(110),
                "exact same inputs: the saved result",
                60,
                GOOD,
            )

    def stagebars(self, img, draw, opts, k):
        """The measured stage times as bars that grow in time-lapse; a cut
        after a stage greys out what the decision does not need."""
        bars = opts["bars"]
        cut = opts.get("cut", [None])[min(k, len(opts.get("cut", [None])) - 1)]
        top = self.px(150) + self.head
        bottom = self.caption_top() - self.px(120)
        step = (bottom - top) / len(bars)
        bh = min(step * 0.7, self.px(84))
        x0, x1 = self.px(280), self.w - self.px(700 if not self.portrait else 260)
        scale = (x1 - x0) / float(max(v for _, v in bars))
        e = self.ease() if opts.get("grow") and k == 0 else 1.0
        f = font(self.px(44))
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

    def cards(self, img, draw, opts, k):
        """Results as cards: a new one slides in for a change; switching back
        brings the old one forward without running anything."""
        items = opts["cards"]
        sel = opts["select"][min(k, len(opts["select"]) - 1)]
        cw, ch = self.px(1.4 * 420), self.px(1.4 * 300)
        y = self.px(1.4 * 220) + self.head
        gap = (self.w - len(items) * cw) / (len(items) + 1)
        for j, (title, sub) in enumerate(items):
            x = gap + j * (cw + gap)
            on = j == sel
            lift = self.px(1.4 * 40) * self.ease() if on else 0
            r = [x, y - lift, x + cw, y + ch - lift]
            draw.rounded_rectangle(
                r,
                radius=self.px(1.4 * 18),
                fill=PANEL,
                outline=ACCENT if on else DIM,
                width=self.px(1.4 * 6 if on else 2),
            )
            self.text_in(draw, [r[0], r[1], r[2], r[1] + ch * 0.55], title, 60, FG)
            self.text_in(
                draw, [r[0], r[1] + ch * 0.5, r[2], r[3]], sub, 48, GOOD if on else DIM
            )


class Voice(object):
    def __init__(self, onnx, config):
        from piper import PiperVoice, SynthesisConfig

        self.voice = PiperVoice.load(onnx, config_path=config)
        self.config = SynthesisConfig(length_scale=LENGTH_SCALE)

    def say(self, text, path):
        """Speak `text` into a WAV at `path`; return (rate, int16 samples)."""
        with wave.open(path, "wb") as w:
            self.voice.synthesize_wav(SCRIPT.say(text), w, syn_config=self.config)
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

        steps = int(ANIM * ANIM_FPS) if opts.get("animate") and seconds > ANIM else 1
        for j in range(steps):
            canvas.t = (j + 1) / float(steps)
            img, draw = canvas.new()
            canvas.head = canvas.px(150) if opts.get("headline") else 0
            getattr(canvas, kind)(img, draw, opts, k)
            canvas.headline(draw, opts, k)
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
