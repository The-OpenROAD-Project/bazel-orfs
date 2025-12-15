"""
Verilog providers for dependency management.
"""

# Provider for verilog dependency information
VerilogInfo = provider(
    doc = "Provider for verilog dependency DAG information",
    fields = {
        "dag": "Depset of DAG entries representing verilog dependencies",
    },
)

def make_dag_entry(srcs, hdrs, includes, data, deps, label, tags):
    """Create a DAG entry for verilog dependency tracking.

    Args:
        srcs: List of source files
        hdrs: List of header files
        includes: List of include paths
        data: List of data files
        deps: List of dependencies
        label: Label of the target
        tags: List of tags

    Returns:
        A struct representing a DAG entry
    """
    return struct(
        srcs = tuple(srcs),
        hdrs = tuple(hdrs),
        includes = tuple(includes),
        data = tuple(data),
        deps = tuple(deps),
        label = label,
        tags = tuple(tags),
    )

def make_verilog_info(new_entries, old_infos):
    """Create a VerilogInfo provider from DAG entries.

    Args:
        new_entries: List of new DAG entries to add
        old_infos: List of existing VerilogInfo providers to merge

    Returns:
        A VerilogInfo provider
    """
    dag = depset(
        direct = new_entries,
        transitive = [info.dag for info in old_infos],
    )
    return VerilogInfo(dag = dag)
