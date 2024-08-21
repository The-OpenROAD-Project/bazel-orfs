#! /bin/sh

set -e

cd "$(dirname "$0")"
if [ -z "$FLOW_HOME" ]; then
  export YOSYS_EXE="${YOSYS_PATH}"
  export OPENROAD_EXE="${OPENROAD_PATH}"
  export KLAYOUT_CMD="${KLAYOUT_PATH}"
  export FLOW_HOME="${FLOW_HOME}"
  export TCL_LIBRARY="${TCL_LIBRARY}"
  export QT_PLUGIN_PATH="${QT_PLUGIN_PATH}"
  export LIBGL_DRIVERS_PATH="${LIBGL_DRIVERS_PATH}"
  export GIO_MODULE_DIR="${GIO_MODULE_DIR}"

  # absolute paths, if non-empty
  export YOSYS_EXE="${YOSYS_EXE:+$PWD/$YOSYS_EXE}"
  export OPENROAD_EXE="${OPENROAD_EXE:+$PWD/$OPENROAD_EXE}"
  export FLOW_HOME="${FLOW_HOME:+$PWD/$FLOW_HOME}"
  export TCL_LIBRARY="${TCL_LIBRARY:+$PWD/$TCL_LIBRARY}"
  export QT_PLUGIN_PATH="${QT_PLUGIN_PATH:+$PWD/$QT_PLUGIN_PATH}"
  export LIBGL_DRIVERS_PATH="${LIBGL_DRIVERS_PATH:+$PWD/$LIBGL_DRIVERS_PATH}"
  export GIO_MODULE_DIR="${GIO_MODULE_DIR:+$PWD/$GIO_MODULE_DIR}"
fi
exec make --file "$FLOW_HOME/Makefile" "$@"
