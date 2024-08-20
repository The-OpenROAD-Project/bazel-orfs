#! /bin/sh

set -e

if [ -z "$FLOW_HOME" ]; then
  export YOSYS_EXE="${YOSYS_PATH}"
  export OPENROAD_EXE="${OPENROAD_PATH}"
  export KLAYOUT_CMD="${KLAYOUT_PATH}"
  export FLOW_HOME="${FLOW_HOME}"
  export TCL_LIBRARY="${TCL_LIBRARY}"
  export QT_PLUGIN_PATH="${QT_PLUGIN_PATH}"
  export LIBGL_DRIVERS_PATH="${LIBGL_DRIVERS_PATH}"
  export GIO_MODULE_DIR="${GIO_MODULE_DIR}"
fi

cd "$(dirname "$0")"
exec make --file "$FLOW_HOME/Makefile" "$@"
