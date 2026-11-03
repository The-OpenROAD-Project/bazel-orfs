"""xs_kit: the XSTile implementation kit and its README.pdf, built from the
flows that make the tile (README: EXPORT.md, kit/)."""

load("@bazel-orfs//:openroad.bzl", "orfs_run")
load("@rules_python//python:defs.bzl", "py_binary", "py_test")
load("//tools/carve:memories.bzl", "carve_memories")

_KIT = "//test/coremark_joule/designs/asap7/xiangshan/kit"
_PDK = "//flow:asap7"

def xs_kit(name, flow, regfiles, sdc, doc_inputs, regfile_specs, rtl_ports, tags = ["manual"]):
    """The kit of `flow`'s synthesis: <name> is the .tar.gz, <name>_readme
    its README.pdf, and `export` writes and unpacks it
    (bazelisk run :export -- <dir>).

    Args:
      name: the archive's target.
      flow: the flow whose synthesis netlist is the kit's, <flow>_synth.
      regfiles: the register files' modules, each a macro of its own
        flow: <module>_generate_abstract and <module>_synth.
      sdc: the design's SDC, which sources the platform's.
      doc_inputs: labels of plan.json, plan.bzl, kpi.json, resources.json
        and the arrays' ab.json, by render_md.py's flag names.
      regfile_specs: the register files' specs.
      rtl_ports: the tile's ports as the RTL declares them (ports.py).

    What README.pdf says about the netlist and the ports is read from
    kit/pinned/, committed with the SHA-256 of the netlist it describes,
    so the README re-renders without a synthesis: <name>_pin is the same, built; `bazelisk run :kit_repin`
    writes it into kit/pinned/, and <name>_pin_test says when the two
    differ.
      tags: forwarded.
    """
    synth = ":%s_synth" % flow
    kit = "$(execpath %s:kit)" % _KIT

    # the platform files the flow read, as the flow resolved them
    orfs_run(
        name = name + "_manifest",
        src = synth,
        outs = [name + "_manifest.txt"],
        script = _KIT + ":kit_manifest.tcl",
        user_arguments = {"OUTPUT": "$(location %s_manifest.txt)" % name},
        tags = tags,
    )

    carve_memories(
        name = name + "_memories",
        lef = name + "_memories.lef",
        lib = name + "_memories.lib",
        srcs = [synth],
        tags = tags,
    )

    native.filegroup(
        name = name + "_netlist",
        srcs = [synth],
        output_group = "1_2_yosys.v",
        tags = tags,
    )
    for m in regfiles:
        native.filegroup(
            name = "%s_%s_netlist" % (name, m),
            srcs = [":%s_synth" % m],
            output_group = "1_2_yosys.v",
            tags = tags,
        )

    pick = kit + " pick --manifest $(location :%s_manifest.txt) --kind %%s $(locations %s)" % (name, _PDK)
    native.genrule(
        name = name + "_sdc",
        srcs = [sdc, ":%s_manifest.txt" % name, _PDK],
        outs = [name + "_doc/XSTile.sdc"],
        cmd = "%s sdc --design $(location %s) --platform $$(%s) --out $@" % (kit, sdc, pick % "platform_sdc"),
        tags = tags,
        tools = [_KIT + ":kit"],
    )
    native.genrule(
        name = name + "_itf",
        srcs = [":%s_manifest.txt" % name, _PDK],
        outs = [name + "_doc/asap7.itf"],
        cmd = "$(execpath %s:itf_gen) --lef $$(%s) --setrc $$(%s) --out $@" % (_KIT, pick % "tech_lef", pick % "setrc"),
        tags = tags,
        tools = [_KIT + ":itf_gen", _KIT + ":kit"],
    )

    # the kit without its README
    regfile_args = " ".join([
        "--regfile %s=$$(echo $(locations :%s_generate_abstract) $(locations :%s_%s_netlist) | tr ' ' ,)" % (m, m, name, m)
        for m in regfiles
    ])
    native.genrule(
        name = name + "_files",
        srcs = [
            ":%s_manifest.txt" % name,
            ":%s_netlist" % name,
            ":%s_sdc" % name,
            ":%s_itf" % name,
            ":%s_memories.lef" % name,
            ":%s_memories.lib" % name,
            _KIT + ":sta.tcl",
            _PDK,
        ] + [":%s_generate_abstract" % m for m in regfiles] + [":%s_%s_netlist" % (name, m) for m in regfiles],
        outs = [name + "_files.tar.gz"],
        cmd = " ".join([
            kit,
            "tar --out $@",
            "--manifest $(location :%s_manifest.txt)" % name,
            "--netlist $(location :%s_netlist)" % name,
            "--sdc $(location :%s_sdc)" % name,
            "--itf $(location :%s_itf)" % name,
            "--sta $(location %s:sta.tcl)" % _KIT,
            "--memories-lef $(location :%s_memories.lef)" % name,
            "--memories-lib $(location :%s_memories.lib)" % name,
            regfile_args,
            "$(locations %s)" % _PDK,
        ]),
        tags = tags,
        tools = [_KIT + ":kit"],
    )

    # the facts README.pdf states, counted in the kit as it ships: the
    # netlist linked against the kit's own LEF and liberty, its SDC read
    native.genrule(
        name = name + "_facts",
        srcs = [":%s_files.tar.gz" % name, _KIT + ":kit_facts.tcl"],
        outs = [name + "_facts.json"],
        cmd = " ".join([
            "d=$(@D)/%s_facts.d; rm -rf $$d; mkdir -p $$d;" % name,
            "%s unpack --in $(location :%s_files.tar.gz) --dir $$d;" % (kit, name),
            "k=$$d/xiangshan-xstile-asap7;",
            "KIT_LEFS=\"$$k/tech/asap7_tech.lef $$(ls $$k/cells/lef/*.lef) $$(ls $$k/macros/lef/*.lef)\"",
            "KIT_LIBS=\"$$(ls $$k/cells/lib/*.lib $$k/macros/lib/*.lib)\"",
            "KIT_NETLIST=$$k/netlist/XSTile.v KIT_TOP=XSTile KIT_SDC=$$k/constraints/XSTile.sdc",
            "KIT_OUT=$@",
            "$(execpath @openroad//:openroad) -no_init -no_splash -threads max -exit $(location %s:kit_facts.tcl) > $(@D)/%s_facts.log 2>&1" % (_KIT, name),
            "|| { tail -50 $(@D)/%s_facts.log; exit 1; };" % name,
            "rm -rf $$d",
        ]),
        tags = tags,
        tools = [_KIT + ":kit", "@openroad//:openroad"],
    )

    # the facts and ports, with the netlist they were computed from (its
    # SHA-256: a commit would not survive the rebase a merge makes): what
    # kit/pinned/ holds once :kit_repin has written it there
    native.genrule(
        name = name + "_pin",
        srcs = [":%s_facts.json" % name, ":%s_netlist" % name, rtl_ports],
        outs = [name + "_pin/facts.json", name + "_pin/rtl_ports.json", name + "_pin/pin.json"],
        cmd = " ".join([
            "cp $(location :%s_facts.json) $(location %s_pin/facts.json) &&" % (name, name),
            "cp $(location %s) $(location %s_pin/rtl_ports.json) &&" % (rtl_ports, name),
            "%s pin --status bazel-out/stable-status.txt --netlist $(location :%s_netlist) --out $(location %s_pin/pin.json)" % (kit, name, name),
        ]),
        # the day of the pin (tools/workspace_status.sh)
        stamp = 1,
        tags = tags,
        tools = [_KIT + ":kit"],
    )

    py_binary(
        name = name + "_repin",
        srcs = [_KIT + ":repin.py"],
        main = _KIT + ":repin.py",
        args = ["$(rootpath :%s_pin/%s)" % (name, f) for f in ("facts.json", "rtl_ports.json", "pin.json")],
        data = [":%s_pin/%s" % (name, f) for f in ("facts.json", "rtl_ports.json", "pin.json")],
        tags = tags,
    )

    # manual: it builds the kit's whole synthesis
    py_test(
        name = name + "_pin_test",
        srcs = [_KIT + ":repin.py"],
        main = _KIT + ":repin.py",
        args = ["--check"] + ["$(rootpath :%s_pin/%s)" % (name, f) for f in ("facts.json", "rtl_ports.json", "pin.json")],
        data = [":%s_pin/%s" % (name, f) for f in ("facts.json", "rtl_ports.json", "pin.json")] + [
            _KIT + ":pinned/facts.json",
            _KIT + ":pinned/pin.json",
            _KIT + ":pinned/rtl_ports.json",
        ],
        tags = tags,
    )

    native.genrule(
        name = name + "_readme",
        srcs = [
            _KIT + ":pinned/facts.json",
            _KIT + ":pinned/rtl_ports.json",
            _KIT + ":pinned/pin.json",
            _KIT + ":EXPORT.md",
            _KIT + ":blocks.json",
            _KIT + ":sta.tcl",
            _KIT + ":xstile_context.svg",
            _KIT + ":clock_boundary.svg",
            "//:MODULE.bazel",
        ] + doc_inputs.values() + regfile_specs,
        outs = [name + "_doc/README.pdf", name + "_doc/README.md", name + "_doc/floorplan.svg"],
        cmd = " ".join([
            "$(execpath %s:render_md)" % _KIT,
            "--template $(location %s:EXPORT.md)" % _KIT,
            "--out $(location %s_doc/README.md)" % name,
            "--svg $(location %s_doc/floorplan.svg)" % name,
            "--facts $(location %s:pinned/facts.json)" % _KIT,
            "--rtl-ports $(location %s:pinned/rtl_ports.json)" % _KIT,
            "--pin $(location %s:pinned/pin.json)" % _KIT,
            " ".join(["--%s $(location %s)" % (k, v) for k, v in sorted(doc_inputs.items())]),
            "--blocks $(location %s:blocks.json)" % _KIT,
            "--module-bazel $(location //:MODULE.bazel)",
            "--sta $(location %s:sta.tcl)" % _KIT,
            "--status bazel-out/stable-status.txt",
            " ".join(["$(location %s)" % s for s in regfile_specs]),
            "&& $(execpath %s:md_to_pdf)" % _KIT,
            "--out $(location %s_doc/README.pdf)" % name,
            "--title 'XiangShan XSTile on ASAP7'",
            "--image floorplan.svg=$(location %s_doc/floorplan.svg)" % name,
            "--image xstile_context.svg=$(location %s:xstile_context.svg)" % _KIT,
            "--image clock_boundary.svg=$(location %s:clock_boundary.svg)" % _KIT,
            "$(location %s_doc/README.md)" % name,
        ]),
        # the commit and the date README.pdf names (tools/workspace_status.sh)
        stamp = 1,
        tags = tags,
        tools = [_KIT + ":render_md", _KIT + ":md_to_pdf"],
    )

    native.genrule(
        name = name,
        srcs = [":%s_files.tar.gz" % name, ":%s_doc/README.pdf" % name],
        outs = ["xiangshan-xstile-asap7.tar.gz"],
        cmd = "%s add --in $(location :%s_files.tar.gz) --out $@ README.pdf=$(location :%s_doc/README.pdf)" % (kit, name, name),
        tags = tags,
        tools = [_KIT + ":kit"],
    )

    py_binary(
        name = "export",
        srcs = [_KIT + ":export.py"],
        main = _KIT + ":export.py",
        data = [":" + name],
        env = {"KIT_ARCHIVE": "$(rootpath :%s)" % name},
        tags = tags,
        deps = [_KIT + ":kit_lib"],
    )
