#!/usr/bin/env python3
"""Analyze Verilog/SystemVerilog module hierarchy.

Parses Verilog files to extract module definitions and instantiations,
then prints a hierarchy tree with instance counts. Useful for planning
hierarchical synthesis and identifying SRAM/macro candidates.

Usage:
    python3 analyze_hierarchy.py <verilog_files_or_dirs...> [--top MODULE]

Example:
    python3 analyze_hierarchy.py rtl/ --top BoomTile
    python3 analyze_hierarchy.py design.sv core.sv mem.sv
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path


def find_verilog_files(paths):
    """Find all .v and .sv files in the given paths."""
    files = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix in ('.v', '.sv'):
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob('*.v')))
            files.extend(sorted(path.rglob('*.sv')))
    return files


def parse_modules(files):
    """Parse module definitions and instantiations from Verilog files.

    Returns:
        modules: dict mapping module_name -> {
            'file': str,
            'instances': list of (instance_module, instance_name),
            'line_count': int,
        }
    """
    modules = {}

    # Patterns
    module_def = re.compile(
        r'^\s*module\s+(\w+)', re.MULTILINE
    )
    endmodule = re.compile(r'^\s*endmodule', re.MULTILINE)
    # Match instantiations: ModuleName [#(...)] instance_name (
    # Exclude keywords that look like instantiations
    KEYWORDS = {
        'module', 'endmodule', 'input', 'output', 'inout', 'wire', 'reg',
        'logic', 'assign', 'always', 'initial', 'begin', 'end', 'if',
        'else', 'for', 'while', 'case', 'endcase', 'function',
        'endfunction', 'task', 'endtask', 'generate', 'endgenerate',
        'parameter', 'localparam', 'integer', 'real', 'genvar',
        'typedef', 'struct', 'enum', 'union', 'interface', 'endinterface',
        'class', 'endclass', 'package', 'endpackage', 'import',
        'assert', 'property', 'sequence', 'covergroup', 'constraint',
    }
    inst_pattern = re.compile(
        r'^\s*(\w+)\s+(?:#\s*\([^)]*\)\s*)?(\w+)\s*\(',
        re.MULTILINE
    )

    for fpath in files:
        try:
            content = fpath.read_text(errors='replace')
        except Exception as e:
            print(f"Warning: could not read {fpath}: {e}", file=sys.stderr)
            continue

        # Strip single-line comments
        content_no_comments = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        # Strip block comments
        content_no_comments = re.sub(r'/\*.*?\*/', '', content_no_comments, flags=re.DOTALL)

        # Find all module definitions and their bodies
        for m in module_def.finditer(content_no_comments):
            mod_name = m.group(1)
            start = m.end()
            end_match = endmodule.search(content_no_comments, start)
            if not end_match:
                continue
            body = content_no_comments[start:end_match.start()]
            line_count = body.count('\n')

            instances = []
            for inst in inst_pattern.finditer(body):
                inst_mod = inst.group(1)
                inst_name = inst.group(2)
                if inst_mod not in KEYWORDS and not inst_mod.startswith('$'):
                    instances.append((inst_mod, inst_name))

            modules[mod_name] = {
                'file': str(fpath),
                'instances': instances,
                'line_count': line_count,
            }

    return modules


def find_top_modules(modules):
    """Find modules that are never instantiated by other modules."""
    instantiated = set()
    for mod_data in modules.values():
        for inst_mod, _ in mod_data['instances']:
            instantiated.add(inst_mod)
    return [m for m in modules if m not in instantiated]


def count_instances(modules):
    """Count how many times each module is instantiated across the design."""
    counts = defaultdict(int)
    for mod_data in modules.values():
        for inst_mod, _ in mod_data['instances']:
            counts[inst_mod] += 1
    return counts


def print_hierarchy(modules, mod_name, inst_counts, indent=0, visited=None):
    """Print module hierarchy tree."""
    if visited is None:
        visited = set()

    prefix = "  " * indent
    mod_data = modules.get(mod_name)

    if mod_data is None:
        print(f"{prefix}|- {mod_name} (external/primitive)")
        return

    lines = mod_data['line_count']
    n_inst = len(mod_data['instances'])
    count_str = f" [x{inst_counts[mod_name]}]" if inst_counts.get(mod_name, 0) > 1 else ""

    marker = ""
    if lines > 500:
        marker = " *** LARGE"
    if inst_counts.get(mod_name, 0) > 2:
        marker += " *** REPEATED"

    print(f"{prefix}|- {mod_name} ({lines} lines, {n_inst} instances){count_str}{marker}")

    if mod_name in visited:
        print(f"{prefix}  (already expanded)")
        return
    visited.add(mod_name)

    # Group instances by module type
    inst_by_type = defaultdict(list)
    for inst_mod, inst_name in mod_data['instances']:
        inst_by_type[inst_mod].append(inst_name)

    for inst_mod, inst_names in sorted(inst_by_type.items()):
        if len(inst_names) > 1:
            print(f"{prefix}  ({len(inst_names)} instances of {inst_mod})")
        print_hierarchy(modules, inst_mod, inst_counts, indent + 1, visited.copy())


def print_summary(modules, inst_counts):
    """Print summary statistics for planning hierarchical synthesis."""
    print("\n" + "=" * 70)
    print("HIERARCHICAL SYNTHESIS CANDIDATES")
    print("=" * 70)

    # Large modules (>200 lines)
    large = [(name, data) for name, data in modules.items() if data['line_count'] > 200]
    large.sort(key=lambda x: -x[1]['line_count'])

    if large:
        print("\nLarge modules (>200 lines, consider as separate macros):")
        for name, data in large:
            count = inst_counts.get(name, 0)
            print(f"  {name:40s} {data['line_count']:6d} lines  {count:3d}x instantiated  ({data['file']})")

    # Repeated modules (instantiated >2 times)
    repeated = [(name, inst_counts[name]) for name in inst_counts if inst_counts[name] > 2 and name in modules]
    repeated.sort(key=lambda x: -x[1])

    if repeated:
        print("\nRepeated modules (>2 instances, likely SRAMs or datapath elements):")
        for name, count in repeated:
            lines = modules[name]['line_count']
            print(f"  {name:40s} {count:3d}x instantiated  {lines:6d} lines")

    # Modules that look like memories/SRAMs
    mem_patterns = re.compile(r'(sram|ram|mem|reg_?file|array|cache|fifo|queue|buffer)', re.IGNORECASE)
    memories = [name for name in modules if mem_patterns.search(name)]
    if memories:
        print("\nPotential memory/SRAM modules (by name pattern):")
        for name in sorted(memories):
            count = inst_counts.get(name, 0)
            lines = modules[name]['line_count']
            print(f"  {name:40s} {lines:6d} lines  {count:3d}x instantiated")

    print()


def main():
    parser = argparse.ArgumentParser(
        description='Analyze Verilog/SystemVerilog module hierarchy'
    )
    parser.add_argument(
        'paths', nargs='+',
        help='Verilog files or directories to analyze'
    )
    parser.add_argument(
        '--top', default=None,
        help='Top-level module name (auto-detected if not specified)'
    )
    args = parser.parse_args()

    files = find_verilog_files(args.paths)
    if not files:
        print("No Verilog files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {len(files)} Verilog files...")
    modules = parse_modules(files)
    print(f"Found {len(modules)} modules.\n")

    inst_counts = count_instances(modules)
    top_modules = find_top_modules(modules)

    if args.top:
        if args.top not in modules:
            print(f"Error: module '{args.top}' not found.", file=sys.stderr)
            print(f"Available top-level candidates: {', '.join(top_modules)}", file=sys.stderr)
            sys.exit(1)
        tops = [args.top]
    else:
        tops = top_modules

    print(f"Top-level module(s): {', '.join(tops)}\n")
    print("=" * 70)
    print("MODULE HIERARCHY")
    print("=" * 70)

    for top in tops:
        print()
        print_hierarchy(modules, top, inst_counts)

    print_summary(modules, inst_counts)


if __name__ == '__main__':
    main()
