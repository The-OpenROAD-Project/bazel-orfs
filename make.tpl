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
  export RUBYLIB="${RUBY_PATH}:${DLN_LIBRARY_PATH}"
  export DLN_LIBRARY_PATH="${DLN_LIBRARY_PATH}"
  export TCL_LIBRARY="${TCL_LIBRARY}"
  export QT_PLUGIN_PATH="${QT_PLUGIN_PATH}"
  export LIBGL_DRIVERS_PATH="${LIBGL_DRIVERS_PATH}"
  export GIO_MODULE_DIR="${GIO_MODULE_DIR}"
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
# Prevents headless synthesis from loading the xcb platform plugin, which
# pulls in libxcb-cursor0 — a library not shipped in the ORFS Docker image.
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
fi

exec $MAKE_PATH --file "$FLOW_HOME/Makefile" "$@"
