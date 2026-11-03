---
name: web-pr-animation
description: >-
  Show a change to OpenROAD's web viewer (an OpenROAD pull request titled "web: ...")
  as a before/after pair of animated PNGs in the pull request's body, the mouse
  pointer drawn in, recorded on asap7 gcd with //tools/pr_anim: the viewer built at
  the merge-base and at the head, a scene written once and played on both, the frames
  checked for anything private, pushed to an `images` branch on the author's fork and
  put in a Before | After table. Use when opening or updating a web: pull request
  whose change can be seen, or when a reviewer asks what a viewer change looks like.
---

# Before/after animations for web viewer pull requests

A web: pull request changes something a person sees and does in the
viewer. Words describe it badly; a reviewer who can watch the pointer do
the same thing in the viewer before and after the change gets it in
seconds. Each animation is a looping APNG, which GitHub shows inline.

The tool is `//tools/pr_anim:record`. It drives a pinned headless Chrome
(`@chrome_headless_shell`, Chrome for Testing, matched to the Playwright
version in `requirements_dev.in`; bump the two together) through a
scene, screenshots each step, and draws the pointer the page asks for
under the mouse (CSS `cursor`): an arrow, a column-resize arrow, the
progress or wait cursor, a hand, an I-beam. A headless browser has no
pointer of its own, so the drawn one is the only one in the picture, and
it changes shape exactly when the page's code changes it.

## Steps

1. **Two viewers.** The web assets are embedded in the `openroad`
   binary. Build it at the pull request's merge-base and at its head,
   in one OpenROAD checkout so the second build is incremental, and copy
   each binary out (`byo-openroad` for the build; `-c opt`):

   ```sh
   git -C <or> checkout --detach $(git -C <or> merge-base origin/master pr)
   git -C <or> submodule update --init --recursive
   (cd <or> && bazelisk build -c opt //:openroad)
   cp $(readlink -f <or>/bazel-bin/openroad) tmp/bin/openroad-base
   ```

   Several web: pull requests on one merge-base share the base binary.

2. **Serve gcd from each.** The odb-debug daemon serves the viewer
   on the flow's own stage, with timing loaded. One daemon per binary,
   each with its own directory:

   ```sh
   bazelisk run //test/odb_debug:gcd_final_odb_debug -- \
       OPENROAD_EXE=$PWD/tmp/bin/openroad-base ODB_DEBUG_DIR=$PWD/tmp/anim/base
   ```

   `daemon.json` in that directory has the `url` to record: the
   viewer on 127.0.0.1, not the token-gated GUI link.

3. **Write the scene once.** A scene is a Python file that sets
   `STEPS` (the step list is in `record.py`'s docstring) and how it is
   framed: `VIEWPORT`, `CLIP` (a selector, usually the panel that
   changed) and `WIDTH`. `tools/pr_anim/scenes/` has the four recorded
   for OpenROAD #11857 to #11860 and the setups they share: open a panel
   from the Windows menu, drag the splitter to widen it, press Update,
   all under `{"recording": False}` so the animation starts on the state
   that matters. Find selectors in `src/web/src` of the pull request, and
   with an `{"eval": ...}` step that returns what the page has. Write the
   scene for the head, where the new control exists; `"optional": True`
   skips a step the base viewer has no control for. Keep it short, 3 to
   8 seconds: show the state, glide the pointer to the problem, act,
   hold the result.

   **Stage the problem, not just the control.** The base viewer must be
   seen doing what the pull request fixes, and a bug often needs a state
   to show: #11858's squeeze shows only on a table measured in the
   default narrow panel and widened afterwards, and #11860's missing busy
   cursor only on a request that takes time. Compare the last frames of
   before and after side by side; if they look alike, the scene is wrong.

4. **Record both.** `bazelisk run` waits for bazel's lock while a
   daemon's `bazelisk run` holds it, so start every daemon first, one
   after another, then record:

   ```sh
   bazelisk run //tools/pr_anim:record -- --url <base url> \
       --scene tools/pr_anim/scenes/11858.py --out tmp/anim/11858-before.png --label before
   bazelisk run //tools/pr_anim:record -- --url <head url> \
       --scene tools/pr_anim/scenes/11858.py --out tmp/anim/11858-after.png --label after
   ```

   Check a state with an `eval` step that prints it, not by eyeballing
   sampled frames: identical frames are merged and their durations
   summed, so frame numbers are not steps. A request that takes seconds
   on a big design takes milliseconds on gcd; `{"ws_delay": ms}` holds
   the viewer's websocket requests so the waiting can be seen, and the
   caption under the table says that it did.

5. **Purge every frame.** The confidentiality purge in CLAUDE.md applies
   to pixels too: look at every distinct frame for a local path, a user
   or host name, a token, a URL with a port, an employer's name. gcd and
   the viewer's own widgets are public; anything else is suspect. The
   APNG carries no text metadata (`frames.write_apng` writes none; its
   test checks it).

6. **Publish.** Push the files to an orphan `images` branch on the
   author's OpenROAD fork, one directory per pull request, and link them
   by their raw URL. Writing to the fork and editing the upstream body
   are upstream writes: only on the human's order.

   ```sh
   git switch --orphan images        # in a scratch clone of the fork
   mkdir -p 11858 && cp tmp/anim/11858-*.png 11858/
   git add 11858 && git commit -s -m "11858: before/after" && git push fork images
   ```

7. **The body.** Put the table under the body's opening paragraph and
   change nothing else in it:

   ```markdown
   | Before | After |
   |---|---|
   | ![before](https://raw.githubusercontent.com/<fork>/OpenROAD/images/11858/before.png) | ![after](https://raw.githubusercontent.com/<fork>/OpenROAD/images/11858/after.png) |

   asap7 gcd, final stage.
   ```

## Checks

- `bazelisk test //tools/pr_anim:frames_test` — the pointer is drawn at
  the hot spot, the APNG animates, loops and carries no metadata.
- `bazelisk test //tools/pr_anim:smoke_test` (manual) — the pinned
  browser runs here and the pointer follows the cursor a local page asks
  for. The browser needs the desktop libraries its `deb.deps` names; a
  bare CI runner may not have them.
