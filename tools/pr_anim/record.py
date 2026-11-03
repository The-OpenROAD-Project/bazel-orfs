#!/usr/bin/env python3
"""Record a scene in OpenROAD's web viewer as an animated PNG.

    bazelisk run //tools/pr_anim:record -- \\
        --url http://127.0.0.1:<port> --scene scene.py --out before.png \\
        --label before

drives the pinned headless Chrome (@chrome_headless_shell) with Playwright
through the steps in scene.py, a screenshot per step, the pointer drawn in
where the mouse is with the cursor the page asks for there, and writes
them as one looping APNG. Run it once against the viewer built at the
pull request's merge-base and once at its head, with the same scene.

A scene is a Python file that sets STEPS, a list of dicts, run in order,
and may set VIEWPORT ("1600x900"), CLIP (a selector to frame, e.g. the
panel that changed) and WIDTH (pixels to scale down to); scenes/ has the
ones recorded for OpenROAD #11857 to #11860.

    {"wait_for": "#timing-widget"}            wait for a selector to show
    {"move": "#hist .bar >> nth=3"}           glide the mouse there
    {"move": [640, 400], "steps": 12}         ...or to a point
    {"drag": "th >> nth=1", "anchor": "right", "by": [200, 0]}
    {"click": "text=Update"}                  move there, then click
    {"dblclick": "..."}  {"key": "Enter"}
    {"eval": "js"}                            run it, print what it returns
    {"ws_delay": 1500}                        hold each websocket request
    {"recording": False}                      setup from here on, no frames
    {"wait": 300}                             let the page settle, no frame
    {"frame": 1500}                           show the current frame 1.5 s

A target is a selector or a point; "anchor" picks a point of the
target's box (center, left, right, top, bottom) and "dx"/"dy" offset it.
"optional": True skips the step when the selector matches nothing: a
control the "before" viewer does not have yet. Every move,
drag and click is drawn as frames on its way. ws_delay is how a request
that takes seconds on a big design is shown on gcd: the caption should
say so.
"""

import argparse
import asyncio
import io
import os
import re
import runpy
import sys

from PIL import Image
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frames as F  # noqa: E402

STEP_MS = 60
CURSOR_JS = """([x, y]) => {
  const e = document.elementFromPoint(x, y);
  const of = (n) => (n ? getComputedStyle(n).cursor : "auto");
  const c = of(e);
  return c === "auto" ? of(document.body) : c;
}"""


def _path(p):
    """A command-line path, relative to where `bazelisk run` was started."""
    base = os.environ.get("BUILD_WORKING_DIRECTORY", os.getcwd())
    return os.path.join(base, p)


class Recorder:
    def __init__(self, page, label, scale, clip=None):
        self.page = page
        self.clip = clip
        self.label = label
        self.scale = scale
        self.mouse = (0.0, 0.0)
        self.frames = []
        self.durations = []
        self.cursors = []
        self.ws_delay_ms = 0
        self.recording = True

    async def frame(self, ms=STEP_MS):
        if not self.recording:
            return
        box = None
        if self.clip:
            box = await self.page.locator(self.clip).first.bounding_box()
        png = await self.page.screenshot(clip=box)
        image = Image.open(io.BytesIO(png)).convert("RGB")
        cursor = await self.page.evaluate(CURSOR_JS, list(self.mouse))
        kind = F.cursor_kind(cursor)
        x, y = self.mouse
        if box:
            x, y = x - box["x"], y - box["y"]
        F.draw_pointer(image, x, y, kind=kind, scale=self.scale)
        if self.label:
            F.caption(image, self.label, scale=self.scale)
        self.frames.append(image)
        self.cursors.append(kind)
        self.durations.append(ms)

    async def point(self, step, key):
        target = step[key]
        if isinstance(target, (list, tuple)):
            x, y = target
        else:
            locator = self.page.locator(target).first
            if step.get("optional") and await locator.count() == 0:
                return None
            box = await locator.bounding_box()
            if box is None:
                raise SystemExit("not visible: %r" % target)
            anchor = step.get("anchor", "center")
            x = {
                "left": box["x"] + 1,
                "right": box["x"] + box["width"] - 1,
            }.get(anchor, box["x"] + box["width"] / 2)
            y = {
                "top": box["y"] + 1,
                "bottom": box["y"] + box["height"] - 1,
            }.get(anchor, box["y"] + box["height"] / 2)
        return x + step.get("dx", 0), y + step.get("dy", 0)

    async def glide(self, x, y, steps):
        x0, y0 = self.mouse
        for i in range(1, steps + 1):
            self.mouse = (x0 + (x - x0) * i / steps, y0 + (y - y0) * i / steps)
            await self.page.mouse.move(*self.mouse)
            await self.frame()

    async def run(self, step):
        steps = step.get("steps", 10)
        for key in ("move", "click", "dblclick", "drag"):
            if key in step and await self.point(step, key) is None:
                return
        if "wait_for" in step:
            await self.page.locator(step["wait_for"]).first.wait_for(
                timeout=step.get("timeout", 120000)
            )
        elif "move" in step:
            await self.glide(*await self.point(step, "move"), steps)
        elif "click" in step or "dblclick" in step:
            key = "click" if "click" in step else "dblclick"
            await self.glide(*await self.point(step, key), steps)
            if key == "click":
                await self.page.mouse.click(*self.mouse)
            else:
                await self.page.mouse.dblclick(*self.mouse)
            await self.frame()
        elif "drag" in step:
            await self.glide(*await self.point(step, "drag"), steps)
            await self.page.mouse.down()
            await self.frame()
            dx, dy = step["by"]
            x0, y0 = self.mouse
            await self.glide(x0 + dx, y0 + dy, steps)
            await self.page.mouse.up()
            await self.frame()
        elif "key" in step:
            await self.page.keyboard.press(step["key"])
            await self.frame()
        elif "eval" in step:
            # A value is printed: how a scene's selectors are found.
            value = await self.page.evaluate(step["eval"])
            if value is not None:
                print(value)
        elif "recording" in step:
            self.recording = step["recording"]
        elif "ws_delay" in step:
            self.ws_delay_ms = step["ws_delay"]
        elif "wait" in step:
            await self.page.wait_for_timeout(step["wait"])
        elif "frame" in step:
            await self.frame(step["frame"])
        else:
            raise SystemExit("unknown step: %r" % (step,))


async def record(args, steps):
    width, height = (int(v) for v in args.viewport.split("x"))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path=os.path.abspath(args.browser), headless=True
        )
        page = await browser.new_page(viewport={"width": width, "height": height})
        rec = Recorder(page, args.label, scale=args.pointer_scale, clip=args.clip)

        async def route(ws):
            server = ws.connect_to_server()

            def to_server(message):
                async def later():
                    await asyncio.sleep(rec.ws_delay_ms / 1000)
                    server.send(message)

                if rec.ws_delay_ms:
                    asyncio.ensure_future(later())
                else:
                    server.send(message)

            ws.on_message(to_server)

        await page.route_web_socket(re.compile(".*"), route)
        await page.goto(args.url)
        for step in steps:
            await rec.run(step)
        await browser.close()
    return rec


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--url", required=True, help="the viewer, as daemon.json's url")
    p.add_argument("--scene", required=True, help="a Python file that sets STEPS")
    p.add_argument("--out", required=True, help="the APNG to write")
    p.add_argument("--label", default="", help='burned in top-left, e.g. "before"')
    p.add_argument("--viewport", help="WxH; default the scene's VIEWPORT")
    p.add_argument(
        "--clip", help="a selector: frame only this element; default the scene's CLIP"
    )
    p.add_argument(
        "--width", type=int, help="scale frames down to; default the scene's WIDTH"
    )
    p.add_argument(
        "--pointer-scale",
        type=float,
        default=1.6,
        help="pointer and label size; 1.6 reads as a desktop pointer at --width",
    )
    p.add_argument("--browser", required=True, help="chrome-headless-shell")
    args = p.parse_args(argv)
    scene = runpy.run_path(_path(args.scene))
    steps = scene["STEPS"]
    # A scene says how it is framed; the command line overrides it.
    args.viewport = args.viewport or scene.get("VIEWPORT", "1280x800")
    args.clip = args.clip or scene.get("CLIP")
    args.width = args.width or scene.get("WIDTH", 960)
    rec = asyncio.run(record(args, steps))
    out = _path(args.out)
    size = F.write_apng(rec.frames, rec.durations, out, width=args.width)
    print("%s: %d frames, %d KiB" % (args.out, len(rec.frames), size // 1024))
    return rec


if __name__ == "__main__":
    main()
