"""ORFS GUI server — bazelisk run //:gui

Persistent Flask server with pywebview (or browser) frontend.
Reads files from bazel-bin/ to display build status, metrics, logs, and reports.
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from gui_src.metrics import MetricsReader
from gui_src.query import QueryRunner

LOCKFILE_NAME = ".gui_port"
HEALTH_TIMEOUT = 2


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get_workspace():
    return os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())


def get_tmp_dir(workspace):
    tmp = Path(workspace) / "tmp"
    tmp.mkdir(exist_ok=True)
    return tmp


def lockfile_path(workspace):
    return get_tmp_dir(workspace) / LOCKFILE_NAME


def write_lockfile(workspace, port):
    path = lockfile_path(workspace)
    path.write_text(json.dumps({"pid": os.getpid(), "port": port}))


def read_lockfile(workspace):
    path = lockfile_path(workspace)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data
    except (json.JSONDecodeError, KeyError):
        path.unlink(missing_ok=True)
        return None


def remove_lockfile(workspace):
    lockfile_path(workspace).unlink(missing_ok=True)


def is_pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def check_existing_server(workspace):
    """Check if a server is already running. Returns port if alive, None otherwise."""
    data = read_lockfile(workspace)
    if data is None:
        return None

    pid = data.get("pid")
    port = data.get("port")
    if not pid or not port:
        remove_lockfile(workspace)
        return None

    if not is_pid_alive(pid):
        remove_lockfile(workspace)
        return None

    # PID is alive — verify it's actually our server with a health check
    import urllib.request

    try:
        url = f"http://127.0.0.1:{port}/api/health"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as resp:
            if resp.status == 200:
                return port
    except Exception:
        pass

    remove_lockfile(workspace)
    return None


def open_browser(port):
    """Open the GUI in the system browser."""
    webbrowser.open(f"http://127.0.0.1:{port}")


def start_webview_blocking(port):
    """Start pywebview on the main thread (blocks until window closes).

    Returns True if webview started, False if unavailable/failed.
    """
    try:
        import webview

        webview.create_window("ORFS GUI", f"http://127.0.0.1:{port}", width=1400, height=900)
        webview.start()  # blocks on main thread until window closes
        return True
    except ImportError:
        print("pywebview not available, falling back to browser")
        return False
    except Exception as e:
        print(f"pywebview failed ({e}), falling back to browser")
        return False


def create_app(workspace):
    bazel_bin = Path(workspace) / "bazel-bin"

    # Prefer workspace source for live reload during development.
    # When run via `bazelisk run`, BUILD_WORKSPACE_DIRECTORY is set and
    # gui_src/static/ in the workspace is the editable source.
    # Fall back to runfiles (read-only) for packaged usage.
    workspace_static = Path(workspace) / "gui_src" / "static"
    runfiles_static = Path(__file__).parent / "static"
    static_dir = workspace_static if workspace_static.is_dir() else runfiles_static

    app = Flask(__name__, static_folder=None)
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    query_runner = QueryRunner(workspace)
    metrics_reader = MetricsReader(bazel_bin)

    @app.after_request
    def no_cache(response):
        """Disable caching so edits to static files are picked up on refresh."""
        if "text/html" in response.content_type or "javascript" in response.content_type or "text/css" in response.content_type:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    @app.route("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(static_dir, filename)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "workspace": workspace})

    @app.route("/api/targets")
    def targets():
        try:
            result = query_runner.get_targets()
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/graph")
    def graph():
        target = request.args.get("target", "//...")
        try:
            result = query_runner.get_graph(target)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/metrics/<path:design_path>")
    def metrics(design_path):
        try:
            result = metrics_reader.get_metrics(design_path)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/logs/<path:design_path>/<stage>")
    def logs(design_path, stage):
        try:
            content = metrics_reader.get_log(design_path, stage)
            return Response(content, mimetype="text/plain")
        except FileNotFoundError:
            return Response("Log not found", status=404)
        except Exception as e:
            return Response(str(e), status=500)

    @app.route("/api/reports/<path:design_path>/<stage>")
    def reports(design_path, stage):
        try:
            content = metrics_reader.get_report(design_path, stage)
            return Response(content, mimetype="text/plain")
        except FileNotFoundError:
            return Response("Report not found", status=404)
        except Exception as e:
            return Response(str(e), status=500)

    @app.route("/api/status")
    def status():
        try:
            result = metrics_reader.get_all_status()
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/cache-check")
    def cache_check():
        """Check if bazel disk cache is configured."""
        cache_configured = False
        cache_path = None
        for rc_name in [".bazelrc", "user.bazelrc"]:
            rc_path = Path(workspace) / rc_name
            if rc_path.exists():
                text = rc_path.read_text()
                for line in text.splitlines():
                    stripped = line.strip()
                    if "disk_cache" in stripped and not stripped.startswith("#"):
                        cache_configured = True
                        # Extract path from --disk_cache=<path>
                        if "=" in stripped:
                            cache_path = stripped.split("=", 1)[1].strip()
                        break
            if cache_configured:
                break
        return jsonify(
            {"configured": cache_configured, "path": cache_path}
        )

    # Track running builds: target -> {proc, log_path, started}
    builds = {}
    build_log_dir = get_tmp_dir(workspace) / "gui_build_logs"
    build_log_dir.mkdir(exist_ok=True)

    @app.route("/api/build/<path:target>", methods=["POST"])
    def build(target):
        """Trigger a bazel build for a target."""
        if target in builds:
            info = builds[target]
            if info["proc"].poll() is None:
                return jsonify({"status": "already_running", "target": target})
        # Ensure target starts with //
        if not target.startswith("//"):
            target = "//" + target
        try:
            safe_name = target.replace("//", "").replace("/", "_").replace(":", "_")
            log_path = build_log_dir / f"{safe_name}.log"
            log_file = open(log_path, "w")
            proc = subprocess.Popen(
                ["bazelisk", "build", target],
                cwd=workspace,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            builds[target] = {
                "proc": proc,
                "log_path": str(log_path),
                "started": time.time(),
            }
            return jsonify({"status": "started", "target": target, "pid": proc.pid})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/builds")
    def list_builds():
        """List running builds and their status."""
        result = {}
        for target, info in list(builds.items()):
            rc = info["proc"].poll()
            elapsed = time.time() - info["started"]
            if rc is None:
                status = "running"
            elif rc == 0:
                status = "success"
            else:
                status = "failed"
            result[target] = {
                "status": status,
                "elapsed": round(elapsed, 1),
                "log_path": info["log_path"],
            }
        return jsonify(result)

    @app.route("/api/build-log/<path:target>")
    def build_log(target):
        """Stream build log for a target."""
        if not target.startswith("//"):
            target = "//" + target
        info = builds.get(target)
        if not info:
            return Response("No build found", status=404)
        try:
            content = Path(info["log_path"]).read_text()
            return Response(content, mimetype="text/plain")
        except OSError:
            return Response("Log not available", status=404)

    @app.route("/api/builds/stop", methods=["POST"])
    def stop_builds():
        """Stop all running builds."""
        stopped = []
        for target, info in list(builds.items()):
            if info["proc"].poll() is None:
                info["proc"].terminate()
                stopped.append(target)
        return jsonify({"stopped": stopped})

    @app.route("/api/events")
    def events():
        """SSE endpoint for live file change notifications."""

        def generate():
            last_check = time.time()
            while True:
                time.sleep(2)
                changes = metrics_reader.check_changes(since=last_check)
                last_check = time.time()
                if changes:
                    yield f"data: {json.dumps(changes)}\n\n"

        return Response(
            generate(), mimetype="text/event-stream"
        )

    return app


def main():
    parser = argparse.ArgumentParser(description="ORFS GUI")
    parser.add_argument(
        "--gui",
        choices=["webview", "browser"],
        default="browser",
        help="GUI mode: webview (native window) or browser (system browser)",
    )
    parser.add_argument(
        "--port", type=int, default=0, help="Port to listen on (0 = auto)"
    )
    args = parser.parse_args()

    workspace = get_workspace()
    print(f"ORFS GUI — workspace: {workspace}")

    # Check for existing server — just open a window to it
    existing_port = check_existing_server(workspace)
    if existing_port:
        print(f"Server already running on port {existing_port}")
        if args.gui == "webview":
            start_webview_blocking(existing_port) or open_browser(existing_port)
        else:
            open_browser(existing_port)
        return

    # Start new server
    port = args.port if args.port else find_free_port()
    app = create_app(workspace)

    write_lockfile(workspace, port)

    def cleanup(signum=None, frame=None):
        remove_lockfile(workspace)
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print(f"Starting server on http://127.0.0.1:{port}")
    print("Press Ctrl-C to stop")

    # Run Flask in a daemon thread so the main thread is free for pywebview
    flask_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, threaded=True),
        daemon=True,
    )
    flask_thread.start()

    # Give Flask a moment to bind
    time.sleep(0.3)

    if args.gui == "webview":
        # pywebview blocks the main thread; closing the window returns here
        if not start_webview_blocking(port):
            open_browser(port)

        # Window closed — server keeps running, wait for Ctrl-C
        print("Window closed. Server still running. Press Ctrl-C to stop.")
    else:
        open_browser(port)

    try:
        # Block main thread until Ctrl-C
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        remove_lockfile(workspace)


if __name__ == "__main__":
    main()
