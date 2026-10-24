"""carve_verilog(): identical tiles carved out of a flat module, the rest left as the parent."""

load("//test/lec:lec.bzl", "lec_test")

_YOSYS = "$(execpath @yosys//:yosys) -q "

# Both sides of the proof as kepler-formal reads them: flat, yosys's simple
# cells, one register per bit, undefined bits tied to 0 alike.
_MAP = "hierarchy -top {top}; flatten -noscopeinfo; proc; techmap; opt_clean; dfflegalize -cell $$_DFF_P_ x -cell $$_DFF_PN0_ x -cell $$_DFF_PN1_ x -cell $$_DLATCH_P_ x -cell $$_DLATCH_N_ x; techmap; opt_clean; setundef -zero; opt_clean"

def _lec_side(src, work, top, out, census = None):
    """Commands: yosys JSON `src` to `out`, a netlist of lec_cells.lib
    cells, through files named `work`.*."""
    return [
        _YOSYS + "-p 'read_json {src}; {map}; write_json {work}.mapped'".format(src = src, work = work, map = _MAP.format(top = top)),
        "$(execpath //tools/carve:lec_names) --json {work}.mapped --top {top} {census}--out {work}.named".format(
            work = work,
            top = top,
            census = "--census {} ".format(census) if census else "",
        ),
        _YOSYS + "-p 'read_json {work}.named; write_verilog -noexpr -noattr {out}'".format(work = work, out = out),
    ]

def carve_verilog(name, srcs, top, spec, negative_control, hdrs = [], read_slang_args = "", include = None, keep_hierarchy = False, lec_timeout = "moderate", tags = []):
    """`name`.v is `top` flattened, its tiles carved out as one module.

    yosys reads `srcs` with slang, flattens `top` and maps its memories to
    registers and logic, as synthesis would; tools/carve/carve.py carves
    the tiles `spec` names; yosys writes the result, and
    `name`_census.json the cells and pins of each tile and the parent.
    `name`_flat.v is the same design uncarved, from the same reading: the
    flat arm of a study, so both arms start from one elaboration.

    `name`_lec_test proves the carved design equivalent to the uncarved
    one, register for register: the carve, and the reuse of the first
    tile's module for every tile. kepler-formal's sequential mode does not
    finish on a design this size; the carve keeps every register, so the
    combinational check between matched registers is the whole proof.
    `name`_negative_control_test reverses the bits of `negative_control`
    (INSTANCE.PORT) and must be refuted.

    Args:
      name: the outputs are `name`.v, `name`_flat.v and `name`_census.json.
      srcs: the design's Verilog.
      hdrs: files the sources include, not read on their own.
      top: the module to carve.
      spec: the carve spec, JSON (tools/carve/carve.py), or a list of
        them, carved one after the other, each its own module.
      negative_control: INSTANCE.PORT, an input the negative control reverses.
      read_slang_args: extra read_slang arguments, e.g. --ignore-timing.
      lec_timeout: the proofs' test timeout; a refutation can take longer
        than a proof, and both grow with the design.
      include: a file in srcs or hdrs whose directory is an include path.
      keep_hierarchy: read the design's hierarchy and let yosys flatten
        it, so every cell's name keeps its instance path: for a spec that
        confines a tile to an instance.
      tags: for every target.
    """

    # outside the single quotes of yosys's -p, so the shell expands it
    inc = "-I '\"$$(dirname $(location {}))\"' ".format(include) if include else ""
    specs = spec if type(spec) == "list" else [spec]
    hier = "--keep-hierarchy " if keep_hierarchy else ""
    d = "$(@D)/" + name

    # the carve: what the flows build from
    native.genrule(
        name = name,
        srcs = srcs + hdrs + specs,
        outs = [
            name + ".v",
            name + "_flat.v",
            name + "_census.json",
            name + "_carved.json",
            name + "_gold.json",
        ],
        cmd = " && ".join([
            _YOSYS + "-m $(execpath @sv-elab//src/yosys_plugin:slang.so) -p " +
            "'read_slang {hier}{args} {inc} --top {top} {srcs}; hierarchy -top {top}; proc; flatten; memory; opt -purge; write_json {d}_flat.json; write_verilog -noattr $(location {name}_flat.v)'".format(
                name = name,
                hier = hier,
                args = read_slang_args,
                inc = inc,
                top = top,
                srcs = " ".join(["$(location {})".format(s) for s in srcs]),
                d = d,
            ),
            "$(execpath //tools/carve:carve) --json {d}_flat.json --top {top} {specs} --out $(location {name}_carved.json) --gold $(location {name}_gold.json) --census $(location {name}_census.json)".format(
                d = d,
                name = name,
                top = top,
                specs = " ".join(["--spec $(location {})".format(x) for x in specs]),
            ),
            _YOSYS + "-p 'read_json $(location {name}_carved.json); hierarchy -check -top {top}; check -assert; write_verilog -noattr $(location {name}.v)'".format(name = name, top = top),
        ]),
        tags = tags,
        tools = [
            "//tools/carve",
            "@sv-elab//src/yosys_plugin:slang.so",
            "@yosys",
        ],
    )

    # both sides of the proof and the negative control: only the proofs
    # read them, so a flow does not wait for them
    w = "$(@D)/" + name + "_lec"
    native.genrule(
        name = name + "_lec",
        srcs = [
            name + "_carved.json",
            name + "_census.json",
            name + "_gold.json",
        ],
        outs = [name + "_lec.v", name + "_gold_lec.v", name + "_broken_lec.v"],
        cmd = " && ".join([
                              "$(execpath //tools/carve:break_port) --json $(location {name}_carved.json) --top {top} --port {port} --out {w}_broken.json".format(name = name, w = w, top = top, port = negative_control),
                          ] + _lec_side("$(location {}_gold.json)".format(name), w + "_gold", top, "$(location {}_gold_lec.v)".format(name)) +
                          _lec_side("$(location {}_carved.json)".format(name), w + "_carved", top, "$(location {}_lec.v)".format(name), "$(location {}_census.json)".format(name)) +
                          _lec_side(w + "_broken.json", w + "_broken", top, "$(location {}_broken_lec.v)".format(name), "$(location {}_census.json)".format(name))),
        tags = tags,
        tools = [
            "//tools/carve:break_port",
            "//tools/carve:lec_names",
            "@yosys",
        ],
    )
    for test, gate, equivalent in [
        (name + "_lec_test", name + "_lec.v", True),
        (name + "_negative_control_test", name + "_broken_lec.v", False),
    ]:
        lec_test(
            name = test,
            expect_equivalent = equivalent,
            # the solver ran: a verdict without a problem proves nothing
            expect_problem_size = True,
            gate_verilog_files = [":" + gate],
            gold_verilog_files = [":" + name + "_gold_lec.v"],
            liberty_files = ["//tools/carve:lec_cells.lib"],
            tags = tags,
            timeout = lec_timeout,
        )
