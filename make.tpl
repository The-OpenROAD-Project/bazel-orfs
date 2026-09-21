#! /bin/sh
set -e

if [ -z "$FLOW_HOME" ]; then
  export MAKE_PATH="${MAKE_PATH}"
  # Yosys-stage runners pass yosys_substitutions(ctx) and get a concrete
  # ${YOSYS_PATH} substituted in. Openroad-stage runners (orfs_final etc.)
  # use only flow_substitutions(ctx) and leave ${YOSYS_PATH} as a literal,
  # which the shell then expands to empty. Only export YOSYS_EXE when
  # we actually got a path; otherwise fall back to the caller's env so
  # `bazel run :_final -- SYNTH_NETLIST_FILES=...` (used by
  # //:make-yosys-netlist for re-synth) can supply yosys via YOSYS_EXE
  # from the user shell.
  if [ -n "${YOSYS_PATH}" ]; then
    export YOSYS_EXE="${YOSYS_PATH}"
  fi
  # A caller-supplied OPENROAD_EXE wins. Pointing a deployed reproducer at
  # a locally built openroad is what the _deps tarball is for, and the
  # deployed tree is the one place the binary is not a bazel label.
  if [ -n "${OPENROAD_EXE:-}" ]; then
    _openroad_exe="$OPENROAD_EXE"
  else
    # Select the Qt-linked openroad only when the caller asked for a
    # gui_* make target. Build-time stages and the portable tarball
    # invoke CLI make targets and therefore keep ${OPENROAD_PATH}.
    _openroad_exe="${OPENROAD_PATH}"
    for _arg in "$@"; do
      case "$_arg" in
        gui_*|gui-*) _openroad_exe="${OPENROAD_QT_PATH}"; break ;;
      esac
    done
  fi
  export OPENROAD_EXE="$_openroad_exe"
  export OPENSTA_EXE="${OPENSTA_PATH}"
  export KLAYOUT_CMD="${KLAYOUT_PATH}"
  export STDBUF_CMD="${STDBUF_PATH}"
  export FLOW_HOME="${FLOW_HOME}"
else
  # if make is not in the path, error out, otherwise set MAKE_PATH
  if ! command -v make >/dev/null; then
    echo "Error: make is not in the PATH"
    exit 1
  fi
  export MAKE_PATH="$(command -v make)"
fi

# https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/issues/3907
export LEC_CHECK=0

# Default to offscreen Qt platform when no display server is available.
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
fi

# A deployed tree holds one stage's inputs as bazel built them. A bare
# stage target (`floorplan`, `place`, ...) lets ORFS's dependency chain
# decide that upstream results are stale and rebuild them here, from
# inputs bazel never gave the tree, and the tree stops matching the
# build. The honest targets are `do-<stage>`, which run that stage and
# nothing else; `run`, `open_*` and `gui_*` pass. Stop before make does.
for _arg in "$@"; do
  case "$_arg" in
    synth|floorplan|place|cts|grt|route|final|generate_abstract|all|clean_all)
      echo "make: refusing target '$_arg' in a deployed tree: it would rebuild upstream" >&2
      echo "      stages from inputs bazel never gave this tree. Run one stage:" >&2
      echo "      ./make do-$_arg   (do-synth, do-floorplan, do-place, do-cts, do-grt, do-route, do-final)" >&2
      exit 2
      ;;
  esac
done
exec $MAKE_PATH --file "$FLOW_HOME/Makefile" "$@"
