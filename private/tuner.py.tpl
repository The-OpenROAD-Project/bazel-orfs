#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(
        description="Standalone executable for an ORFS stage.",
        epilog="Use cases: AI iteration, debugging in gdb, whittle.py, hyperparameter tuning."
    )
    parser.add_argument("--byo-openroad-cmd-line", action="store_true", help="Print standalone command line for gdb or BYO openroad.")
    parser.add_argument("--variable", action="append", default=[], help="Override variables, e.g. PLACE_DENSITY=0.6")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary execution directory instead of deleting it")
    parser.add_argument("--tmp-dir", help="Directory to create the temporary execution folder in")
    parser.add_argument("--log-file", help="File to redirect OpenROAD stdout/stderr to")
    parser.add_argument("--source", action="append", default=[], help="Path to Tcl files to source before the main script")
    parser.add_argument("--tcl-command", action="append", default=[], help="Tcl commands to run before the main script")
    parser.add_argument("--output", help="Output file path (optional).")
    parser.add_argument("--cmd", help="Override the make target (if running via make).", default=None)
    
    args, unknown = parser.parse_known_args()

    # The template expands the ENV_JSON
    raw_env_json = '%{ENV_JSON}'
    base_env = json.loads(raw_env_json)
    
    # Resolve RUNFILES
    # When bazel runs this script, RUNFILES_DIR is set. If we run directly, we might need to find it.
    runfiles_dir = os.environ.get("RUNFILES_DIR", os.path.abspath(sys.argv[0] + ".runfiles"))
    runfiles_dir = os.path.abspath(runfiles_dir)
    # HACK: find the actual runfiles dir if sys.argv[0] is messed up
    if not os.path.exists(runfiles_dir):
        # Look for the nearest .runfiles
        curr = os.path.abspath(sys.argv[0])
        while curr != "/":
            if curr.endswith(".runfiles"):
                runfiles_dir = curr
                break
            curr = os.path.dirname(curr)
    
    # replace $RUNFILES in base_env
    resolved_env = {}
    for k, v in base_env.items():
        if isinstance(v, str):
            val = v
            # Handle old-style external/ path resolution in bzlmod since RUNFILES is flat
            if "_main/external/" in val:
                val = val.replace("_main/external/", "")
            elif "external/" in val:
                val = val.replace("external/", "")
            val = val.replace("$RUNFILES", runfiles_dir)
            resolved_env[k] = val
        else:
            resolved_env[k] = str(v)
            
    # apply overrides from args.variable
    for var in args.variable:
        if "=" in var:
            k, v = var.split("=", 1)
            resolved_env[k] = v
            
    # positional KEY=VALUE overrides (to match old run_executable behavior if needed)
    for arg in unknown:
        if "=" in arg:
            k, v = arg.split("=", 1)
            resolved_env[k] = v
            
    env = dict(os.environ)
    env.update(resolved_env)
    
    if args.output:
        env["OUTPUT"] = args.output

    openroad_exe = resolved_env.get("OPENROAD_EXE", "openroad")
    run_script = resolved_env.get("RUN_SCRIPT")
    if not run_script:
        sys.exit("RUN_SCRIPT not found in environment.")

    # FLOW_HOME is necessary for SCRIPTS_DIR resolution in ORFS if missing
    if "SCRIPTS_DIR" not in resolved_env and "FLOW_HOME" in resolved_env:
        resolved_env["SCRIPTS_DIR"] = os.path.join(resolved_env["FLOW_HOME"], "scripts")
        
    if "WORK_HOME" not in resolved_env:
        # Default WORK_HOME is inside runfiles to ensure input lookup works
        # If we are in runfiles_dir context, we need to map to the root of the workspace
        # and include the bazel package directory since hack_away_prefix stripped it
        pkg = resolved_env.get("BAZEL_PACKAGE", "")
        resolved_env["WORK_HOME"] = os.path.join(runfiles_dir, "_main", pkg)
    else:
        # If it's not absolute, it's relative to the workspace root in runfiles
        if not os.path.isabs(resolved_env["WORK_HOME"]):
            resolved_env["WORK_HOME"] = os.path.join(runfiles_dir, "_main", resolved_env["WORK_HOME"])

    # Make file paths absolute (hack_away_prefix removed the package path, so they are relative to WORK_HOME)
    # Wait! If they are relative, they MUST be joined with WORK_HOME not just "_main"!
    # Wait, in raw_env_json they are "test/results...", which IS relative to "_main"!
    for var in ["ODB_FILE", "SDC_FILE", "DESIGN_CONFIG"]:
        if var in resolved_env and not os.path.isabs(resolved_env[var]):
            resolved_env[var] = os.path.join(runfiles_dir, "_main", resolved_env[var])

    if "RESULTS_DIR" not in resolved_env:
        if "ODB_FILE" in resolved_env:
            resolved_env["RESULTS_DIR"] = os.path.dirname(resolved_env["ODB_FILE"])
        else:
            resolved_env["RESULTS_DIR"] = os.path.join(resolved_env["WORK_HOME"], "results")
    if "REPORTS_DIR" not in resolved_env:
        resolved_env["REPORTS_DIR"] = os.path.join(resolved_env["WORK_HOME"], "reports")
    if "LOG_DIR" not in resolved_env:
        resolved_env["LOG_DIR"] = os.path.join(resolved_env["WORK_HOME"], "logs")
    if "OBJECTS_DIR" not in resolved_env:
        resolved_env["OBJECTS_DIR"] = os.path.join(resolved_env["WORK_HOME"], "objects")

    # Override with arguments passed explicitly on the command line
    for var in args.variable:
        if "=" in var:
            k, v = var.split("=", 1)
            resolved_env[k] = v
            # If they pass ODB_FILE, make it absolute again relative to cwd
            if k in ["ODB_FILE", "SDC_FILE", "DESIGN_CONFIG"] and not os.path.isabs(v):
                resolved_env[k] = os.path.abspath(v)

    # HACK for test/cell_count.tcl and other scripts: 
    # They often rely on the CWD being set to the directory containing results/
    # In Bazel, the default cwd is the workspace root or the runfiles root, but
    # for external packages or subpackages we need to run from WORK_HOME so that
    # paths like `results/2_floorplan.odb` (which some tcl scripts construct) work!
    # BUT wait, some scripts like cell_count.tcl just read `2_floorplan.odb` directly
    # from the current directory. Let's just set the cwd to the directory containing the ODB file!
    work_dir = resolved_env.get("WORK_HOME", os.getcwd())
    if "ODB_FILE" in resolved_env:
        work_dir = os.path.dirname(resolved_env["ODB_FILE"])
        
    # Variables that are typically populated by the ORFS make wrappers or variables.yaml but could be missing
    if "LIB_FILES" not in resolved_env:
        resolved_env["LIB_FILES"] = ""
    if "OPENROAD_HIERARCHICAL" not in resolved_env:
        resolved_env["OPENROAD_HIERARCHICAL"] = "0"
    if "DESIGN_CONFIG" in resolved_env and os.path.exists(resolved_env["DESIGN_CONFIG"]):
        with open(resolved_env["DESIGN_CONFIG"], "r") as f:
            for line in f:
                if line.startswith("export "):
                    # export VAR?=VALUE
                    parts = line[7:].split("?=", 1)
                    if len(parts) == 2:
                        var = parts[0].strip()
                        val = parts[1].strip()
                        if var not in resolved_env:
                            resolved_env[var] = val
                            
    # Make PLATFORM_DIR absolute if we extracted it
    if "PLATFORM_DIR" in resolved_env and not os.path.isabs(resolved_env["PLATFORM_DIR"]):
        val = resolved_env["PLATFORM_DIR"]
        if val.startswith("external/"):
            resolved_env["PLATFORM_DIR"] = os.path.join(runfiles_dir, val[9:])
        else:
            resolved_env["PLATFORM_DIR"] = os.path.join(runfiles_dir, "_main", val)

    # Generate a TCL wrapper that sets all the environment variables as defaults,
    # then sources the original RUN_SCRIPT.
    import tempfile
    
    # Determine base tmpdir
    base_tmpdir = args.tmp_dir
    if not base_tmpdir:
        base_tmpdir = os.environ.get("TEST_TMPDIR")
    
    # Use a unique temp directory for concurrency
    tmpdir = tempfile.mkdtemp(dir=base_tmpdir, prefix="orfs_tuner_")
    
    wrapper_tcl_path = os.path.join(tmpdir, "tuner_wrapper.tcl")
    
    # Re-evaluate env now that all paths are resolved
    env = dict(os.environ)
    env.update(resolved_env)
    if args.output:
        env["OUTPUT"] = args.output
        
    with open(wrapper_tcl_path, "w") as f:
        f.write("# Generated wrapper for BYO openroad / debugging\n")
        
        # Do a simple $(VAR) substitution pass in Python before writing to TCL
        import re
        def resolve_vars(v):
            def repl(m):
                varname = m.group(1)
                return resolved_env.get(varname, os.environ.get(varname, ""))
            # Evaluate $(VAR)
            return re.sub(r'\$\(([A-Za-z0-9_]+)\)', repl, str(v))
            
        for k, v in resolved_env.items():
            v_eval = resolve_vars(v)
            # escape backslashes, quotes, and tcl specials
            v_escaped = v_eval.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('[', '\\[').replace(']', '\\]')
            f.write(f'if {{![info exists ::env({k})]}} {{ set ::env({k}) "{v_escaped}" }}\n')
            
        # Mock scripts don't have LIB_FILES passed by bazel, so set units explicitly
        f.write('catch { set_cmd_units -time ns -capacitance pF -current mA -voltage V -resistance kOhm -distance um }\n')
        
        # Inject dynamic Tcl configurations
        for src in args.source:
            # make sure it is absolute
            src_abs = src if os.path.isabs(src) else os.path.abspath(src)
            f.write(f'source "{src_abs}"\n')
            
        for cmd_str in args.tcl_command:
            f.write(f'{cmd_str}\n')
            
        f.write(f'source "{run_script}"\n')

    metrics = os.path.join(tmpdir, "metrics.json")
    cmd = [openroad_exe, "-exit", "-metrics", metrics, "-no_init", wrapper_tcl_path]

    if args.byo_openroad_cmd_line:
        print(" ".join(cmd))
        if not args.keep:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        return

    # Run it
    log_file = None
    if args.log_file:
        log_file = open(args.log_file, "w")
    
    try:
        if log_file:
            subprocess.run(cmd, env=env, cwd=work_dir, stdout=log_file, stderr=subprocess.STDOUT, check=True)
        else:
            subprocess.run(cmd, env=env, cwd=work_dir, check=True)
            
        # If success, print the metrics json to stdout
        if os.path.exists(metrics):
            with open(metrics, "r") as mf:
                sys.stdout.write(mf.read())
                
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"\\nError: OpenROAD run failed. ")
        if args.log_file:
            sys.stderr.write(f"See log file: {args.log_file}\\n")
        if not args.keep:
            sys.stderr.write(f"Use --keep to inspect the temporary wrapper script.\\n")
        sys.exit(e.returncode)
    finally:
        if log_file:
            log_file.close()
        if args.keep:
            sys.stderr.write(f"\\nKept temporary execution directory: {tmpdir}\\n")
        else:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

if __name__ == "__main__":
    main()
