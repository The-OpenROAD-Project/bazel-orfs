"""Frames of a recorded web viewer session: the pointer drawn in, an APNG out.

A headless browser has no mouse pointer to show, so record.py logs where
its mouse is and which cursor the page asks for there (CSS `cursor`), and
draw_pointer() paints that cursor onto the screenshot. write_apng() writes
the frames as one animated PNG, which GitHub shows inline in a PR body.
"""

import io

from PIL import Image, ImageDraw, ImageFont

# The arrow, tip at (0, 0), in pixels at scale 1.
_ARROW = [(0, 0), (0, 17), (4, 13), (7, 20), (10, 19), (7, 12), (12, 12)]
# CSS cursor values drawn as something other than the arrow.
_RESIZE = {"col-resize", "ew-resize", "e-resize", "w-resize"}
_BUSY = {"progress", "wait"}
_HAND = {"pointer"}
_TEXT = {"text"}


def cursor_kind(css_cursor):
    """The pointer to draw for a CSS cursor value; unknown ones are an arrow."""
    value = (css_cursor or "").split(",")[-1].strip()
    if value in _RESIZE:
        return "col-resize"
    if value in _BUSY:
        return value
    if value in _HAND:
        return "pointer"
    if value in _TEXT:
        return "text"
    return "arrow"


def _outlined(draw, points, fill="black", outline="white"):
    draw.polygon(points, fill=fill, outline=outline, width=2)


def draw_pointer(image, x, y, kind="arrow", scale=1.0):
    """Paint the pointer for `kind` with its hot spot at (x, y), in place."""
    draw = ImageDraw.Draw(image)

    def at(points, dx=0, dy=0):
        return [(x + (px + dx) * scale, y + (py + dy) * scale) for px, py in points]

    if kind == "col-resize":
        # A double arrow across a two-line bar, as browsers draw col-resize.
        _outlined(draw, at([(-3, -10), (3, -10), (3, 10), (-3, 10)]))
        _outlined(
            draw,
            at(
                [
                    (-12, 0),
                    (-7, -5),
                    (-7, -2),
                    (7, -2),
                    (7, -5),
                    (12, 0),
                    (7, 5),
                    (7, 2),
                    (-7, 2),
                    (-7, 5),
                ]
            ),
        )
        draw.line(at([(0, -9), (0, 9)]), fill="white", width=max(1, int(scale)))
    elif kind == "text":
        _outlined(draw, at([(-1, -9), (1, -9), (1, 9), (-1, 9)]))
        _outlined(draw, at([(-4, -10), (4, -10), (4, -8), (-4, -8)]))
        _outlined(draw, at([(-4, 8), (4, 8), (4, 10), (-4, 10)]))
    elif kind == "pointer":
        _outlined(
            draw,
            at(
                [
                    (0, 0),
                    (3, 0),
                    (3, 7),
                    (10, 8),
                    (11, 18),
                    (1, 18),
                    (-3, 10),
                    (0, 9),
                ],
                dx=-1,
            ),
        )
    else:
        _outlined(draw, at(_ARROW))
    if kind in _BUSY:
        # The spinner beside the arrow (progress) or in its place (wait).
        cx, cy = (x + 18 * scale, y + 20 * scale) if kind == "progress" else (x, y)
        r = 7 * scale
        box = [cx - r, cy - r, cx + r, cy + r]
        draw.ellipse(box, fill="white", outline="black", width=max(1, int(scale)))
        draw.pieslice(box, 270, 360, fill="black")
        draw.pieslice(box, 90, 180, fill="black")
    return image


def caption(image, text, scale=1.0):
    """A label in the top-left corner: "before" or "after"."""
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=int(18 * scale))
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    pad = 6 * scale
    draw.rectangle(
        [0, 0, right - left + 2 * pad, bottom - top + 2 * pad], fill=(0, 0, 0)
    )
    draw.text((pad - left, pad - top), text, fill=(255, 255, 255), font=font)
    return image


def write_apng(frames, durations_ms, out, width=None):
    """Write `frames` (PIL images) as an animated PNG that loops forever.

    `durations_ms` holds one display time per frame. `width` scales every
    frame down to it, keeping the aspect ratio. No metadata is written:
    PIL writes none for a PNG unless asked. Returns the bytes written.
    """
    if not frames:
        raise ValueError("no frames to write")
    if len(frames) != len(durations_ms):
        raise ValueError(
            "%d frames but %d durations" % (len(frames), len(durations_ms))
        )
    images = [f.convert("RGB") for f in frames]
    if width is not None and images[0].width > width:
        height = round(images[0].height * width / images[0].width)
        images = [im.resize((width, height), Image.LANCZOS) for im in images]
    buf = io.BytesIO()
    images[0].save(
        buf,
        format="PNG",
        save_all=True,
        append_images=images[1:],
        duration=list(durations_ms),
        loop=0,
        optimize=True,
    )
    data = buf.getvalue()
    with open(out, "wb") as f:
        f.write(data)
    return len(data)
