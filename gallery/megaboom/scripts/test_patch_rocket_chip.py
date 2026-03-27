#!/usr/bin/env python3
"""Tests for patch_rocket_chip.py.

Tests run against a mock rocket-chip source tree created in a temp directory.
"""

import os
import shutil
import tempfile
import textwrap
import unittest

# Import the module under test
import sys

sys.path.insert(0, os.path.dirname(__file__))
import patch_rocket_chip as prc


class TempRocketChipMixin:
    """Creates a minimal mock rocket-chip source tree for testing."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="rc-patch-test-")
        self.root = self.tmpdir

        # Create directory structure
        for d in [
            "src/main/scala/tilelink",
            "src/main/scala/devices/tilelink",
            "src/main/scala/devices/debug",
            "src/main/scala/subsystem",
            "src/main/scala/rocket",
            "src/main/scala/amba/axi4",
            "src/main/scala/util",
            "src/main/scala/diplomacy",
        ]:
            os.makedirs(os.path.join(self.root, d), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def write_file(self, rel_path: str, content: str) -> str:
        path = os.path.join(self.root, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(textwrap.dedent(content))
        return path

    def read_file(self, rel_path: str) -> str:
        with open(os.path.join(self.root, rel_path)) as f:
            return f.read()


class TestPatchMonitor(TempRocketChipMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write_file(
            "src/main/scala/tilelink/Monitor.scala",
            """\
            package freechips.rocketchip.tilelink

            import chisel3._
            import freechips.rocketchip.formal.{MonitorDirection, IfThen, Property, PropertyClass, TestplanTestType, TLMonitorStrictMode}

            class TLMonitor(args: TLMonitorArgs, monitorDir: MonitorDirection = MonitorDirection.Monitor) extends TLMonitorBase(args)
            {
              require (args.edge.params(TLMonitorStrictMode) || (! args.edge.params(TestplanTestType).formal))

              val cover_prop_class = PropertyClass.Default

              def monAssert(cond: Bool, message: String): Unit =
              if (monitorDir == MonitorDirection.Monitor) {
                assert(cond, message)
              } else {
                Property(monitorDir, cond, message, PropertyClass.Default)
              }

              Property(
                  MonitorDirection.Monitor,
                  (sym_source === sym_source_d),
                  "sym_source should remain stable",
                  PropertyClass.Default)

              monAssert(IfThen(my_resp_pend, !my_a_first_beat), "msg")
              assume(IfThen(my_clr, (my_set || my_pend)), "msg2")

              if (args.edge.params(TestplanTestType).simulation) {
                if (args.edge.params(TLMonitorStrictMode)) {
                  legalizeADSource(bundle, edge)
                }
              }
            }
            """,
        )

    def test_formal_import_replaced(self):
        prc.patch_monitor(self.root)
        text = self.read_file("src/main/scala/tilelink/Monitor.scala")
        assert "import freechips.rocketchip.formal" not in text
        assert "case object TLMonitorStrictMode" in text
        assert "case object TestplanTestType" in text
        assert "object MonitorDirection" in text
        assert "object PropertyClass" in text

    def test_property_calls_removed(self):
        prc.patch_monitor(self.root)
        text = self.read_file("src/main/scala/tilelink/Monitor.scala")
        assert "Property(" not in text
        assert "// Property removed" in text

    def test_multiline_property_removed(self):
        prc.patch_monitor(self.root)
        text = self.read_file("src/main/scala/tilelink/Monitor.scala")
        # The multi-line Property call should be completely gone
        assert "sym_source should remain stable" not in text
        assert "PropertyClass.Default)" not in text

    def test_ifthen_replaced(self):
        prc.patch_monitor(self.root)
        text = self.read_file("src/main/scala/tilelink/Monitor.scala")
        assert "IfThen(" not in text
        # Should be replaced with && expression
        assert "(my_resp_pend && !my_a_first_beat)" in text
        assert "(my_clr && (my_set || my_pend))" in text

    def test_cover_prop_class_removed(self):
        prc.patch_monitor(self.root)
        text = self.read_file("src/main/scala/tilelink/Monitor.scala")
        assert "val cover_prop_class" not in text

    def test_production_code_preserved(self):
        prc.patch_monitor(self.root)
        text = self.read_file("src/main/scala/tilelink/Monitor.scala")
        # These should still be present
        assert "class TLMonitor" in text
        assert "monitorDir == MonitorDirection.Monitor" in text
        assert "TestplanTestType).simulation" in text
        assert "TLMonitorStrictMode)" in text
        assert "legalizeADSource" in text

    def test_monitor_direction_type_fixed(self):
        prc.patch_monitor(self.root)
        text = self.read_file("src/main/scala/tilelink/Monitor.scala")
        # Enumeration type requires .Value suffix
        assert "monitorDir: MonitorDirection.Value = MonitorDirection.Monitor" in text

    def test_missing_file_returns_skip(self):
        os.remove(os.path.join(self.root, "src/main/scala/tilelink/Monitor.scala"))
        changes = prc.patch_monitor(self.root)
        assert any("SKIP" in c for c in changes)


class TestRemoveUnittestCode(TempRocketChipMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        # File with production + test code
        self.write_file(
            "src/main/scala/tilelink/Arbiter.scala",
            """\
            package freechips.rocketchip.tilelink

            import chisel3._

            class TLArbiter {
              // production code here
              val x = 42
            }

            import freechips.rocketchip.unittest._

            class TLArbiterTest(implicit p: Parameters) extends UnitTest(timeout) {
              // test code here
            }
            """,
        )
        # File with NO test code
        self.write_file(
            "src/main/scala/tilelink/Buffer.scala",
            """\
            package freechips.rocketchip.tilelink

            class TLBuffer {
              val y = 99
            }
            """,
        )
        # File in excluded directory (should not be touched)
        self.write_file(
            "src/main/scala/unittest/UnitTest.scala",
            """\
            package freechips.rocketchip.unittest
            import freechips.rocketchip.unittest._
            class UnitTest {}
            """,
        )

    def test_truncates_from_unittest_import(self):
        prc.remove_unittest_test_code(self.root)
        text = self.read_file("src/main/scala/tilelink/Arbiter.scala")
        assert "TLArbiter" in text
        assert "val x = 42" in text
        assert "UnitTest" not in text
        assert "TLArbiterTest" not in text

    def test_preserves_files_without_unittest(self):
        prc.remove_unittest_test_code(self.root)
        text = self.read_file("src/main/scala/tilelink/Buffer.scala")
        assert "TLBuffer" in text
        assert "val y = 99" in text

    def test_skips_excluded_directories(self):
        prc.remove_unittest_test_code(self.root)
        text = self.read_file("src/main/scala/unittest/UnitTest.scala")
        # Should be unchanged
        assert "class UnitTest" in text


class TestRemovePureTestFiles(TempRocketChipMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write_file("src/main/scala/tilelink/Fuzzer.scala", "test file")
        self.write_file(
            "src/main/scala/tilelink/RegisterRouterTest.scala", "test file"
        )
        self.write_file("src/main/scala/amba/axi4/Test.scala", "test file")
        self.write_file("src/main/scala/amba/axi4/Delayer.scala", "test file")
        self.write_file("src/main/scala/devices/tilelink/TestRAM.scala", "test file")
        self.write_file("src/main/scala/diplomacy/Main.scala", "cli tool")

    def test_removes_all_test_files(self):
        prc.remove_pure_test_files(self.root)
        for rel in [
            "src/main/scala/tilelink/Fuzzer.scala",
            "src/main/scala/tilelink/RegisterRouterTest.scala",
            "src/main/scala/amba/axi4/Test.scala",
            "src/main/scala/amba/axi4/Delayer.scala",
            "src/main/scala/devices/tilelink/TestRAM.scala",
            "src/main/scala/diplomacy/Main.scala",
        ]:
            assert not os.path.exists(
                os.path.join(self.root, rel)
            ), f"{rel} should have been removed"


class TestCreateDebugStubs(TempRocketChipMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        # Create original debug files that should be replaced
        self.write_file(
            "src/main/scala/devices/debug/Debug.scala",
            "package freechips.rocketchip.devices.debug\nclass Debug {}",
        )
        self.write_file(
            "src/main/scala/devices/debug/DMI.scala",
            "package freechips.rocketchip.devices.debug\nclass DMI {}",
        )

    def test_creates_stub_file(self):
        prc.create_debug_stubs(self.root)
        stub_path = os.path.join(
            self.root, "src/main/scala/devices/debug/Stubs.scala"
        )
        assert os.path.exists(stub_path)

    def test_stub_has_required_types(self):
        prc.create_debug_stubs(self.root)
        text = self.read_file("src/main/scala/devices/debug/Stubs.scala")
        assert "case class DebugModuleParams" in text
        assert "case object DebugModuleKey" in text
        assert "object DefaultDebugModuleParams" in text
        assert "class TLDebugModule" in text
        assert "trait HasPeripheryDebug" in text
        assert "case object ExportDebug" in text
        assert "case object JTAG" in text
        assert "case object APB" in text

    def test_stub_has_debug_entry_fields(self):
        """CSR.scala accesses debugEntry, debugException, nDscratch."""
        prc.create_debug_stubs(self.root)
        text = self.read_file("src/main/scala/devices/debug/Stubs.scala")
        assert "def debugEntry" in text
        assert "def debugException" in text
        assert "def nDscratch" in text

    def test_removes_original_debug_files(self):
        prc.create_debug_stubs(self.root)
        assert not os.path.exists(
            os.path.join(self.root, "src/main/scala/devices/debug/Debug.scala")
        )
        assert not os.path.exists(
            os.path.join(self.root, "src/main/scala/devices/debug/DMI.scala")
        )

    def test_stub_package_declaration(self):
        prc.create_debug_stubs(self.root)
        text = self.read_file("src/main/scala/devices/debug/Stubs.scala")
        assert "package freechips.rocketchip.devices.debug" in text


class TestPatchBootROM(TempRocketChipMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write_file(
            "src/main/scala/devices/tilelink/BootROM.scala",
            """\
            package freechips.rocketchip.devices.tilelink

            object BootROM {
              case ResourceFileName(fileName) => {
                val file = os.resource / os.RelPath(fileName.dropWhile(_ == '/'))
                os.read.bytes(file)
              }
            }
            """,
        )

    def test_replaces_os_lib_calls(self):
        prc.patch_bootrom(self.root)
        text = self.read_file("src/main/scala/devices/tilelink/BootROM.scala")
        assert "os.resource" not in text
        assert "os.read.bytes" not in text
        assert "os.RelPath" not in text
        assert "getResourceAsStream" in text
        assert "readAllBytes" in text

    def test_preserves_package(self):
        prc.patch_bootrom(self.root)
        text = self.read_file("src/main/scala/devices/tilelink/BootROM.scala")
        assert "package freechips.rocketchip.devices.tilelink" in text

    def test_missing_file_returns_skip(self):
        os.remove(
            os.path.join(
                self.root, "src/main/scala/devices/tilelink/BootROM.scala"
            )
        )
        changes = prc.patch_bootrom(self.root)
        assert any("SKIP" in c for c in changes)


class TestFullPipeline(TempRocketChipMixin, unittest.TestCase):
    """Integration test: run all patches on a realistic mock tree."""

    def setUp(self):
        super().setUp()
        # Monitor.scala with formal deps
        self.write_file(
            "src/main/scala/tilelink/Monitor.scala",
            """\
            package freechips.rocketchip.tilelink
            import chisel3._
            import freechips.rocketchip.formal.{MonitorDirection, IfThen, Property, PropertyClass, TestplanTestType, TLMonitorStrictMode}
            class TLMonitor(args: TLMonitorArgs, monitorDir: MonitorDirection = MonitorDirection.Monitor) extends TLMonitorBase(args) {
              def monAssert(cond: Bool, message: String): Unit =
              if (monitorDir == MonitorDirection.Monitor) { assert(cond, message) }
              else { Property(monitorDir, cond, message, PropertyClass.Default) }
            }
            """,
        )
        # Fuzzer (pure test)
        self.write_file(
            "src/main/scala/tilelink/Fuzzer.scala", "// test file"
        )
        # SRAM with test code at end
        self.write_file(
            "src/main/scala/tilelink/SRAM.scala",
            """\
            package freechips.rocketchip.tilelink
            class TLRAM { val x = 1 }

            import freechips.rocketchip.unittest._
            class TLRAMTest extends UnitTest(500000) {}
            """,
        )
        # Debug files
        self.write_file(
            "src/main/scala/devices/debug/Debug.scala", "original debug"
        )
        # BootROM
        self.write_file(
            "src/main/scala/devices/tilelink/BootROM.scala",
            """\
            package freechips.rocketchip.devices.tilelink
            object BootROM {
              case ResourceFileName(fileName) => {
                val file = os.resource / os.RelPath(fileName.dropWhile(_ == '/'))
                os.read.bytes(file)
              }
            }
            """,
        )

    def test_all_patches_apply_cleanly(self):
        """Run the full patch pipeline and verify no broken references remain."""
        prc.remove_pure_test_files(self.root)
        prc.remove_unittest_test_code(self.root)
        prc.create_debug_stubs(self.root)
        prc.patch_monitor(self.root)
        prc.patch_bootrom(self.root)

        # Fuzzer should be gone
        assert not os.path.exists(
            os.path.join(self.root, "src/main/scala/tilelink/Fuzzer.scala")
        )

        # SRAM should have production code but no test code
        sram = self.read_file("src/main/scala/tilelink/SRAM.scala")
        assert "class TLRAM" in sram
        assert "UnitTest" not in sram

        # Monitor should have stubs but no formal imports
        monitor = self.read_file("src/main/scala/tilelink/Monitor.scala")
        assert "import freechips.rocketchip.formal" not in monitor
        assert "Property(" not in monitor
        assert "class TLMonitor" in monitor

        # Debug stubs should exist
        assert os.path.exists(
            os.path.join(
                self.root, "src/main/scala/devices/debug/Stubs.scala"
            )
        )

        # BootROM should not reference os-lib
        bootrom = self.read_file(
            "src/main/scala/devices/tilelink/BootROM.scala"
        )
        assert "os.resource" not in bootrom


if __name__ == "__main__":
    unittest.main()
