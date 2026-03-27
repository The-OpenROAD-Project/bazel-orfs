#!/usr/bin/env python3
"""Patch rocket-chip for Chisel 7 compatibility.

Removes or stubs out references to excluded packages (formal, unittest,
devices/debug) and replaces os-lib calls with Java stdlib equivalents.

Usage:
    python3 patch_rocket_chip.py <rocket-chip-root>

This script is run by Bazel's patch_cmds during http_archive fetch.
"""

import argparse
import glob
import os
import re
import sys


def patch_monitor(root: str) -> list[str]:
    """Stub out formal verification in Monitor.scala.

    The formal package is excluded from compilation. Monitor.scala imports
    MonitorDirection, IfThen, Property, PropertyClass, TestplanTestType,
    and TLMonitorStrictMode from it. We replace the import with inline
    stubs that preserve the same API surface.
    """
    path = os.path.join(root, "src/main/scala/tilelink/Monitor.scala")
    if not os.path.exists(path):
        return [f"SKIP: {path} not found"]

    with open(path) as f:
        text = f.read()

    changes = []

    # Replace formal import with inline stubs
    old_import = (
        "import freechips.rocketchip.formal."
        "{MonitorDirection, IfThen, Property, PropertyClass, "
        "TestplanTestType, TLMonitorStrictMode}"
    )
    stub = """\
// formal stubs — original package excluded for Chisel 7 compat
import org.chipsalliance.cde.config.Field
case object TLMonitorStrictMode extends Field[Boolean](false)
case object TestplanTestType extends Field[TestplanTestTypeStub](new TestplanTestTypeStub)
class TestplanTestTypeStub { val formal = false; val simulation = false }
object MonitorDirection extends Enumeration { val Monitor, Receiver, Transmitter = Value; implicit class Ops(v: Value) { def flip: Value = v } }
object PropertyClass { val Default = 0 }"""

    if old_import in text:
        text = text.replace(old_import, stub)
        changes.append("Replaced formal import with inline stubs")

    # Replace Property(...) calls — both inline and multi-line forms.
    # Can't use simple non-greedy .*? because calls contain nested parens like
    # (sym_source === sym_source_d). Instead, count parens for balanced matching.
    def remove_property_calls(text: str) -> tuple[str, int]:
        count = 0
        while True:
            idx = text.find("Property(")
            if idx == -1:
                break
            # Find matching closing paren by counting nesting
            depth = 0
            end = idx + len("Property")
            for i in range(end, len(text)):
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            text = text[:idx] + "// Property removed" + text[end:]
            count += 1
        return text, count

    text, n = remove_property_calls(text)
    if n:
        changes.append(f"Removed {n} Property() calls")

    # Replace IfThen(a, b) with (a && b) — it's just a logical implication helper
    text, n = re.subn(
        r"\bIfThen\(([^,]+),\s*([^)]+)\)",
        r"(\1 && \2)",
        text,
    )
    if n:
        changes.append(f"Replaced {n} IfThen() calls with && expressions")

    # Remove cover_prop_class line
    text = text.replace(
        "val cover_prop_class = PropertyClass.Default",
        "// cover_prop_class removed (formal)",
    )

    # Fix MonitorDirection type annotation: Enumeration uses .Value as the type
    text = text.replace(
        "monitorDir: MonitorDirection = MonitorDirection.Monitor",
        "monitorDir: MonitorDirection.Value = MonitorDirection.Monitor",
    )
    # Fix MonitorDirection comparisons to use .Value type
    text = text.replace(
        "monitorDir == MonitorDirection.Monitor",
        "monitorDir == MonitorDirection.Monitor",
    )

    with open(path, "w") as f:
        f.write(text)

    return changes or ["No changes needed"]


def remove_unittest_test_code(root: str) -> list[str]:
    """Remove test classes that depend on the excluded unittest package.

    Pattern: test code is appended at the end of files that also contain
    production code. The import line marks the boundary — everything from
    `import freechips.rocketchip.unittest` onward is test code.
    """
    changes = []
    for path in sorted(
        glob.glob(os.path.join(root, "src/main/scala/**/*.scala"), recursive=True)
    ):
        # Skip excluded directories
        rel = os.path.relpath(path, root)
        skip_dirs = [
            "src/main/scala/groundtest/",
            "src/main/scala/unittest/",
            "src/main/scala/formal/",
            "src/main/scala/examples/",
            "src/main/scala/system/",
            "src/main/scala/devices/debug/",
        ]
        if any(rel.startswith(d) for d in skip_dirs):
            continue

        with open(path) as f:
            text = f.read()

        # Find the unittest import and truncate from there
        match = re.search(r"\nimport freechips\.rocketchip\.unittest\.", text)
        if match:
            new_text = text[: match.start()] + "\n"
            with open(path, "w") as f:
                f.write(new_text)
            changes.append(f"Truncated test code from {rel}")

    return changes or ["No unittest references found"]


def remove_stale_test_imports(root: str) -> list[str]:
    """Remove import lines referencing deleted test types.

    After truncating test code, some files retain imports for TLFuzzer,
    TLRAMModel, LFSR64 etc. that were in the import block above the
    unittest boundary. Remove these stale imports.
    """
    # Types that only exist in deleted test files
    stale_types = [
        "TLFuzzer", "TLRAMModel", "LFSR64", "LFSRNoiseMaker",
        "TLDelayer",
    ]
    pattern = re.compile(
        r"^import .*\b(" + "|".join(stale_types) + r")\b.*$",
        re.MULTILINE,
    )

    changes = []
    for path in sorted(
        glob.glob(os.path.join(root, "src/main/scala/**/*.scala"), recursive=True)
    ):
        rel = os.path.relpath(path, root)
        skip_dirs = [
            "src/main/scala/groundtest/",
            "src/main/scala/unittest/",
            "src/main/scala/formal/",
            "src/main/scala/examples/",
            "src/main/scala/system/",
        ]
        if any(rel.startswith(d) for d in skip_dirs):
            continue

        with open(path) as f:
            text = f.read()

        new_text = pattern.sub("// import removed (test type deleted)", text)
        if new_text != text:
            with open(path, "w") as f:
                f.write(new_text)
            changes.append(f"Removed stale test imports from {rel}")

    return changes or ["No stale imports found"]


def remove_pure_test_files(root: str) -> list[str]:
    """Remove files that are entirely test code."""
    files_to_remove = [
        "src/main/scala/tilelink/Fuzzer.scala",
        "src/main/scala/tilelink/RegisterRouterTest.scala",
        "src/main/scala/amba/axi4/Test.scala",
        "src/main/scala/amba/axi4/Delayer.scala",
        "src/main/scala/devices/tilelink/TestRAM.scala",
        "src/main/scala/diplomacy/Main.scala",
    ]
    changes = []
    for rel in files_to_remove:
        path = os.path.join(root, rel)
        if os.path.exists(path):
            os.remove(path)
            changes.append(f"Removed {rel}")
    return changes or ["No files to remove"]


def create_debug_stubs(root: str) -> list[str]:
    """Create a stub file for the excluded devices/debug package.

    Several production files (CSR.scala, PMA.scala, TLB.scala, subsystem/*.scala)
    import DebugModuleKey and related types from devices/debug. Rather than
    patching each file individually, we create a minimal stub package that
    provides the same types.
    """
    stub_dir = os.path.join(root, "src/main/scala/devices/debug")
    os.makedirs(stub_dir, exist_ok=True)

    stub_content = """\
// Stub for excluded debug package — provides type-compatible API surface
// so that production code (CSR.scala, PMA.scala, TLB.scala, subsystem/)
// can compile without the full debug infrastructure.

package freechips.rocketchip.devices.debug

import chisel3._
import chisel3.util._
import org.chipsalliance.cde.config._
import org.chipsalliance.diplomacy.lazymodule._

case class DebugModuleParams(
  baseAddress: BigInt = BigInt(0),
  nDMIAddrSize: Int = 7,
  nProgramBufferWords: Int = 16,
  nAbstractDataWords: Int = 4,
  nScratch: Int = 1,
  hasBusMaster: Boolean = false,
  clockGate: Boolean = true,
  maxSupportedSBAccess: Int = 32,
  supportQuickAccess: Boolean = false,
  supportHartArray: Boolean = true,
  nHaltGroups: Int = 1,
  nExtTriggers: Int = 0,
  hasHartResets: Boolean = false,
  hasImplicitEbreak: Boolean = false,
  hasAuthentication: Boolean = false,
  crossingHasSafeReset: Boolean = true,
) {
  def address: freechips.rocketchip.diplomacy.AddressSet = freechips.rocketchip.diplomacy.AddressSet(baseAddress, 0xFFF)
  def atzero: Boolean = (baseAddress == 0)
  def nAbstractInstructions: Int = if (atzero) 2 else 5
  def debugEntry: BigInt = baseAddress + 0x800
  def debugException: BigInt = baseAddress + 0x808
  def nDscratch: Int = if (atzero) 1 else 2
}

object DefaultDebugModuleParams {
  def apply(xlen: Int): DebugModuleParams = {
    new DebugModuleParams().copy(
      nAbstractDataWords = (if (xlen == 32) 1 else if (xlen == 64) 2 else 4),
      maxSupportedSBAccess = xlen
    )
  }
}

case object DebugModuleKey extends Field[Option[DebugModuleParams]](Some(DebugModuleParams()))

case class ExportDebugCfg(protocols: Set[DebugExportProtocol] = Set.empty)
sealed trait DebugExportProtocol
case object JTAG extends DebugExportProtocol
case object APB extends DebugExportProtocol
case object ExportDebug extends Field[ExportDebugCfg](ExportDebugCfg())

// Stub LazyModule — provides the type but does nothing.
// intnode is referenced by HasHierarchicalElements even when debugOpt=None
// (compiler still type-checks the .map lambda).
class TLDebugModule(implicit p: Parameters) extends LazyModule {
  import freechips.rocketchip.interrupts._
  val intnode = IntSyncSourceNode(alreadyRegistered = false)
  lazy val module = new LazyModuleImp(this) {}
}

// Stub trait — mixes into subsystem classes
trait HasPeripheryDebug { this: LazyModule =>
  val debugOpt: Option[TLDebugModule] = None
}
"""

    stub_path = os.path.join(stub_dir, "Stubs.scala")
    with open(stub_path, "w") as f:
        f.write(stub_content)

    # Remove all other files in the debug directory (they have heavy deps)
    changes = [f"Created {os.path.relpath(stub_path, root)}"]
    for path in glob.glob(os.path.join(stub_dir, "*.scala")):
        if path != stub_path:
            os.remove(path)
            changes.append(f"Removed {os.path.relpath(path, root)}")

    return changes


def patch_bootrom(root: str) -> list[str]:
    """Replace os-lib calls in BootROM.scala with Java stdlib.

    BootROM uses os.resource/os.RelPath/os.read.bytes to load ROM content.
    Replace with Java NIO equivalents.
    """
    path = os.path.join(root, "src/main/scala/devices/tilelink/BootROM.scala")
    if not os.path.exists(path):
        return [f"SKIP: {path} not found"]

    with open(path) as f:
        text = f.read()

    changes = []

    # Replace the os.resource/os.read.bytes block using regex to handle
    # varying indentation levels
    text, n = re.subn(
        r"val file = os\.resource / os\.RelPath\(fileName\.dropWhile\(_ == '/'\)\)\n"
        r"(\s*)os\.read\.bytes\(file\)",
        "val stream = getClass.getResourceAsStream(\"/\" + fileName.dropWhile(_ == '/'))\n"
        r"\1val bytes = stream.readAllBytes(); stream.close(); bytes",
        text,
    )
    if n:
        changes.append("Replaced os.resource/os.read.bytes with getResourceAsStream")

    with open(path, "w") as f:
        f.write(text)

    return changes or ["No changes needed"]


def patch_annotations(root: str) -> list[str]:
    """Fix json4s API change in Annotations.scala.

    json4s 4.0.5 removed jackson.JsonMethods (pretty, render). Replace
    the json4s serialization with a manual JSON string builder.
    GenRegDescsAnno.serialize is only used for metadata — correctness
    doesn't matter for RTL generation, only compilation.
    """
    path = os.path.join(root, "src/main/scala/util/Annotations.scala")
    if not os.path.exists(path):
        return [f"SKIP: {path} not found"]

    with open(path) as f:
        text = f.read()

    changes = []

    # Remove json4s imports
    text = text.replace(
        "import org.json4s.JsonDSL._\n"
        "import org.json4s.jackson.JsonMethods.{pretty, render}",
        "// json4s imports removed (API changed in 4.x)",
    )

    # Replace the serialize method body with a simple string representation
    text = text.replace(
        '    pretty(render(\n'
        '      ("peripheral" -> (\n'
        '        ("displayName" -> name) ~\n'
        '          ("baseAddress" -> s"0x${base.toInt.toHexString}") ~\n'
        '          ("regfields" -> regDescs)))))',
        '    s"""{"peripheral":{"displayName":"$name","baseAddress":"0x${base.toInt.toHexString}","regfields":${regDescs.size}}}"""',
    )

    if "json4s imports removed" in text:
        changes.append("Replaced json4s serialization in Annotations.scala")

    with open(path, "w") as f:
        f.write(text)

    return changes or ["No changes needed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Path to rocket-chip source root")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print what would be done"
    )
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(os.path.join(root, "src/main/scala")):
        print(f"ERROR: {root} doesn't look like a rocket-chip source tree", file=sys.stderr)
        sys.exit(1)

    steps = [
        ("Remove pure test files", remove_pure_test_files),
        ("Remove unittest test code", remove_unittest_test_code),
        ("Remove stale test imports", remove_stale_test_imports),
        ("Create debug package stubs", create_debug_stubs),
        ("Patch Monitor.scala (formal)", patch_monitor),
        ("Patch BootROM.scala (os-lib)", patch_bootrom),
        ("Patch Annotations.scala (json4s)", patch_annotations),
    ]

    for name, func in steps:
        print(f"\n=== {name} ===")
        if args.dry_run:
            print("  (dry run)")
            continue
        changes = func(root)
        for c in changes:
            print(f"  {c}")

    print("\nDone.")


if __name__ == "__main__":
    main()
