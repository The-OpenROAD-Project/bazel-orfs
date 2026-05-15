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
  export OPENROAD_EXE="${OPENROAD_PATH}"
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

exec $MAKE_PATH --file "$FLOW_HOME/Makefile" "$@"
