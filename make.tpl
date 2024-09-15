#! /bin/sh

set -e

cd "$(dirname "$0")"
if [ -z "$FLOW_HOME" ]; then
  export MAKE_PATH="${MAKE_PATH}"
  export YOSYS_EXE="${YOSYS_PATH}"
  export OPENROAD_EXE="${OPENROAD_PATH}"
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

if [ -n "${EXTRA_ENVS}" ] && [ -f "${EXTRA_ENVS}" ]; then
  source "${EXTRA_ENVS}"
fi

exec $MAKE_PATH --file "$FLOW_HOME/Makefile" "$@"
