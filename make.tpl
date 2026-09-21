#! /bin/sh
set -e

# A deployed tree is one where FLOW_HOME arrives from the template rather
# than from the build's environment; that is where the stage-target guard
# at the bottom applies.
if [ -z "$FLOW_HOME" ]; then
  _deployed=1
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
  _deployed=
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

# A deployed tree holds one stage's inputs exactly as bazel built them. A
# bare stage target lets ORFS's dependency chain decide that an upstream
# result is stale and rebuild it here, from inputs bazel never gave the
# tree, and what the tree runs stops matching what the build produced.
# The honest targets are the `do-` ones, which run that stage and nothing
# else; `run`, `open_*` and `gui_*` pass. Stop before make does.
#
# `for _arg do` and not `for _arg in "$@"`: the rules substitute the
# literal "$@" in this template to inject DESIGN_CONFIG, so spelling it
# here would put that assignment into the loop's word list.
if [ -n "$_deployed" ]; then
  _stages="do-yosys, do-floorplan, do-place, do-cts, do-grt, do-route, do-final"
  for _arg do
    case "$_arg" in
      # ORFS spells the synthesis step do-yosys; there is no do-synth.
      synth) _why="rebuild"; _hint="Run one stage: ./make do-yosys" ;;
      floorplan|place|cts|grt|route|final|generate_abstract)
        _why="rebuild"; _hint="Run one stage: ./make do-$_arg" ;;
      # `all` chains every stage, and `clean_all` deletes what bazel
      # staged here; neither has a single-stage form.
      all) _why="rebuild"; _hint="Run one stage at a time: ./make $_stages" ;;
      clean_all)
        _why="delete"
        _hint="Re-deploy the _deps tree instead." ;;
      *) continue ;;
    esac
    if [ "$_why" = "delete" ]; then
      echo "make: refusing target '$_arg' in a deployed tree: it deletes results" >&2
      echo "      bazel staged here, which this tree cannot rebuild." >&2
    else
      echo "make: refusing target '$_arg' in a deployed tree: it would rebuild" >&2
      echo "      upstream stages from inputs bazel never gave this tree." >&2
    fi
    echo "      $_hint" >&2
    exit 2
  done
fi

exec $MAKE_PATH --file "$FLOW_HOME/Makefile" "$@"
