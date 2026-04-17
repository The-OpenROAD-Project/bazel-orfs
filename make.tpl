#! /bin/sh
set -e

if [ -z "$FLOW_HOME" ]; then
  export MAKE_PATH="${MAKE_PATH}"
  export YOSYS_EXE="${YOSYS_PATH}"
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
