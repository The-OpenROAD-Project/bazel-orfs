"""
Intenteded to provide a way to limit the number of running job
instances of a certain type by using Bazel's worker mechanism.

https://bazel.build/remote/persistent#number-of-workers

This is less than ideal, hopefully more fine grained control
over job scheduling will be provided in the future:

https://github.com/bazelbuild/bazel/issues/27950
https://github.com/bazelbuild/bazel/pull/28013

In short, this mechanism allows us to add
--worker_max_instances=FirGeneration=N to a bazel invocation.
"""

import sys
import json
import subprocess
import os
from urllib import request


def main():
    # Loop forever, reading requests from Stdin (Persistent Worker Protocol)
    while True:
        try:
            # 1. Read a single line (JSON request)
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line)

            # 2. Extract arguments
            # The 'arguments' field contains the flags passed in ctx.actions.run
            raw_args = request.get("arguments", [])
            final_args = []

            # 3. Expand Param Files (@filename)
            # Bazel often passes arguments inside a file to avoid command-line length limits.
            # We must detect this and read the file to get the real command.
            for arg in raw_args:
                if arg.startswith("@"):
                    param_file_path = arg[1:]  # Strip the leading '@'
                    try:
                        with open(param_file_path, "r") as f:
                            # Bazel param files are usually one argument per line
                            # or shell-quoted. For 'multiline', strip whitespace.
                            file_args = [l.strip() for l in f.readlines()]
                            final_args.extend(file_args)
                    except Exception as e:
                        # If we can't read the param file, fail gracefully
                        final_args.append(
                            arg)  # Keep original arg just in case
                        print(
                            f"Error reading param file {param_file_path}: {e}",
                            file=sys.stderr)
                else:
                    final_args.append(arg)

            # 4. Run the Tool (Verilator, Firtool, Generator, etc.)
            # The first argument in final_args is the tool executable itself.
            try:
                # We run the actual command.
                # Note: The worker stays alive, so we must capture output, not print directly.
                result = subprocess.run(
                    final_args,
                    capture_output=True,
                    text=True,
                    env=os.environ  # Pass through environment (PATH, etc.)
                )

                exit_code = result.returncode
                output = result.stderr + result.stdout  # Combine output for Bazel

            except Exception as e:
                exit_code = 1
                output = f"Worker Execution Error: {str(e)}"

            req_id = request.get("requestId")
            if req_id is None:
                req_id = 0

            response = {
                "exitCode": exit_code,
                "output": output,
                "requestId": req_id
            }

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except Exception as e:
            # Catch-all for protocol errors to prevent the worker from crashing silently
            # and hanging the build.
            # We try to report this failure if we have a valid request ID, otherwise just print to stderr.
            err_msg = f"Worker Protocol Error: {str(e)}"
            sys.stderr.write(err_msg + "\n")

            # Attempt to send a failure response if possible
            try:
                response = {
                    "exitCode": 1,
                    "output": err_msg,
                    "requestId": request.get("requestId", 0)
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            except:
                pass


if __name__ == "__main__":
    main()
