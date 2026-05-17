#!/usr/bin/env python3
"""Mock Blender binary for testing the BlenderGDS-driven flow.

Replaces real Blender with a seconds-fast stub that:
- Accepts Blender's `--background --factory-startup --python SCRIPT -- ARGS...`
  argv shape.
- Installs a fake `bpy` module in `sys.modules` so the inner script's
  `import bpy` resolves to our stub.
- Records every `bpy.ops.*` call on a `_calls` list on the stub for
  introspection by callers (e.g. tests).
- Honours the file-side effects that matter for build-graph correctness:
  `bpy.ops.wm.save_as_mainfile(filepath=…)` writes a minimal .blend file
  and `bpy.ops.export_scene.gltf(filepath=…)` writes a GLB stub.
- Exec's the inner script with the post-`--` arguments as its argv.

Mirrors the mock-klayout / mock-openroad approach: just enough of the
real tool's surface for the build graph to flow, fast enough to run in
unit tests, no actual rendering. The fake `bpy.types.Scene` is an
attribute-bag so the addon's `bpy.types.Scene.X = StringProperty(...)`
property-registration pattern works without a Blender runtime.
"""

import os
import runpy
import sys
import types


# Minimal `.blend` magic header. Real Blender files start with "BLENDER"
# + endianness byte + pointer-size byte + version. Just enough so
# downstream consumers recognise the file as non-empty / a blend file.
_BLEND_STUB = b"BLENDER-v404\x00\x00\x00"

# Minimal glTF binary (GLB) header — a 12-byte header followed by an
# empty JSON chunk. Enough to satisfy a "is this a GLB?" magic check.
_GLB_STUB = (
    b"glTF"                  # magic
    b"\x02\x00\x00\x00"       # version 2
    b"\x14\x00\x00\x00"       # total length: 12-byte header + 8-byte JSON chunk header
    + b"\x00\x00\x00\x00"     # JSON chunk length: 0
    + b"JSON"                 # JSON chunk type
)


class _FakeOp:
    """Callable that records its kwargs and returns Blender's success set.

    Real `bpy.ops.<area>.<op>(...)` returns a set like {"FINISHED"} on
    success, {"CANCELLED"} on failure. We always return {"FINISHED"}.
    """

    def __init__(self, name, recorder, side_effect=None):
        self._name = name
        self._recorder = recorder
        self._side_effect = side_effect

    def __call__(self, *args, **kwargs):
        self._recorder.append((self._name, args, kwargs))
        if self._side_effect is not None:
            self._side_effect(*args, **kwargs)
        return {"FINISHED"}


class _OpNamespace:
    """Nested attribute lookup: `bpy.ops.import_scene.gdsii(...)`.

    Unknown ops are auto-created as no-op _FakeOp instances so the
    stub doesn't have to enumerate every Blender op anyone might call.
    """

    def __init__(self, recorder, prefix=""):
        self._recorder = recorder
        self._prefix = prefix
        # Pre-installed side effects for ops we want to actually write
        # files for. Keyed by full dotted op name.
        self._side_effects = {
            "wm.save_as_mainfile": _write_blend_stub,
            "export_scene.gltf": _write_glb_stub,
        }

    def __getattr__(self, name):
        full = "{}.{}".format(self._prefix, name) if self._prefix else name
        if "." not in full and full not in ("wm", "preferences",
                                            "import_scene", "export_scene"):
            # Unknown top-level area — still allow nested lookup. Fall
            # through to creating a sub-namespace.
            pass
        # Heuristic: if the next character would be the operator (i.e.
        # we already have an area prefix), wrap as _FakeOp. Otherwise
        # nest deeper.
        if "." in full:
            return _FakeOp(full, self._recorder, self._side_effects.get(full))
        return _OpNamespace(self._recorder, full)


class _ContextScene:
    """Attribute bag — addon code does `bpy.context.scene.foo = bar`."""
    pass


class _Context:
    def __init__(self):
        self.scene = _ContextScene()


class _Types:
    """Holds `Scene`, which addons mutate by setting class-level attrs
    in their register_properties() routine.
    """

    class Scene:
        pass


def _write_blend_stub(*_args, **kwargs):
    """File-side effect for bpy.ops.wm.save_as_mainfile."""
    filepath = kwargs.get("filepath")
    if filepath:
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(_BLEND_STUB)


def _write_glb_stub(*_args, **kwargs):
    """File-side effect for bpy.ops.export_scene.gltf."""
    filepath = kwargs.get("filepath")
    if filepath:
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(_GLB_STUB)


def make_fake_bpy():
    """Build a fresh fake bpy module. Returned for direct test access too."""
    bpy = types.ModuleType("bpy")
    bpy._calls = []
    bpy.ops = _OpNamespace(bpy._calls)
    bpy.context = _Context()
    bpy.types = _Types()
    return bpy


def _parse_blender_argv(argv):
    """Pull SCRIPT path and inner argv out of Blender's invocation form.

    Real Blender accepts the flags in any order; we only honour the
    subset that BlenderGDS uses:
      --background           -> headless mode (ignored here)
      --factory-startup      -> skip user prefs (ignored here)
      --python SCRIPT        -> the script to run
      --                     -> separator; everything after is the
                                script's argv

    Returns (script_path, inner_argv). Either may be empty/None if not
    given (the caller decides whether to error).
    """
    script = None
    inner = []
    i = 0
    seen_dashdash = False
    while i < len(argv):
        a = argv[i]
        if seen_dashdash:
            inner.append(a)
        elif a == "--":
            seen_dashdash = True
        elif a == "--python" and i + 1 < len(argv):
            script = argv[i + 1]
            i += 1
        elif a in ("--background", "-b", "--factory-startup"):
            pass  # silently accepted
        # Unknown flags are silently ignored — real Blender errors, but
        # we'd rather not break tests that pass flags we don't yet model.
        i += 1
    return script, inner


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Recognise --version probes, matching real Blender's output format
    # closely enough that scripts grepping for "Blender" succeed.
    if argv and argv[0] in ("--version", "-v"):
        print("Blender 4.2.0 (mock)")
        return 0

    script, inner = _parse_blender_argv(argv)
    if script is None:
        # No --python given. Real Blender opens a GUI; we just exit ok.
        return 0

    # Install the fake bpy in sys.modules BEFORE running the script so
    # `import bpy` inside it resolves to our stub.
    sys.modules["bpy"] = make_fake_bpy()

    # Blender hands the script its post-`--` args via sys.argv. Real
    # Blender sets sys.argv[0] to the script path; do the same.
    saved_argv = sys.argv
    sys.argv = [script] + inner
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit as e:
        # The inner script signalling an error — propagate.
        return e.code if isinstance(e.code, int) else 1
    finally:
        sys.argv = saved_argv
    return 0


if __name__ == "__main__":
    sys.exit(main())
