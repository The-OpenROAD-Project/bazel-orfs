#!/usr/bin/env python3
"""Unit tests for patcher.py."""

import argparse
import os
import struct
import tempfile
import unittest

import patcher


def _build_elf64(
    interp=None,
    needed=None,
    rpath=None,
    runpath=None,
    endian="<",
):
    """Build a minimal 64-bit ELF binary in memory.

    Returns bytes of a valid ELF with the requested fields.
    """
    if needed is None:
        needed = []

    # Build .dynstr section contents
    dynstr = b"\x00"  # index 0 is always empty
    needed_offsets = []
    for lib in needed:
        needed_offsets.append(len(dynstr))
        dynstr += lib.encode() + b"\x00"
    rpath_offset = None
    if rpath is not None:
        rpath_offset = len(dynstr)
        dynstr += rpath.encode() + b"\x00"
    runpath_offset = None
    if runpath is not None:
        runpath_offset = len(dynstr)
        dynstr += runpath.encode() + b"\x00"

    # Build .dynamic section
    dyn_entries = []
    for off in needed_offsets:
        dyn_entries.append(struct.pack(endian + "qQ", 1, off))  # DT_NEEDED
    if rpath_offset is not None:
        dyn_entries.append(struct.pack(endian + "qQ", 15, rpath_offset))  # DT_RPATH
    if runpath_offset is not None:
        dyn_entries.append(struct.pack(endian + "qQ", 29, runpath_offset))  # DT_RUNPATH
    # DT_STRTAB — will be patched with actual address
    dyn_entries.append(struct.pack(endian + "qQ", 5, 0))  # placeholder
    dyn_entries.append(struct.pack(endian + "qQ", 0, 0))  # DT_NULL
    dynamic = b"".join(dyn_entries)

    # Build PT_INTERP content
    interp_bytes = b""
    if interp is not None:
        interp_bytes = interp.encode() + b"\x00"

    # Layout:
    # [ELF header 64B] [phdrs] [shdrs] [interp] [dynamic] [dynstr]
    ehdr_size = 64
    phdr_size = 56
    shdr_size = 64

    num_phdrs = 0
    if interp is not None:
        num_phdrs += 1
    if needed or rpath is not None or runpath is not None:
        num_phdrs += 1  # PT_DYNAMIC

    # We need 2 section headers: null + .dynstr
    num_shdrs = 2

    phdrs_offset = ehdr_size
    shdrs_offset = phdrs_offset + num_phdrs * phdr_size
    interp_offset = shdrs_offset + num_shdrs * shdr_size
    dynamic_offset = interp_offset + len(interp_bytes)
    dynstr_offset = dynamic_offset + len(dynamic)

    # Patch DT_STRTAB to point to dynstr virtual address
    # (for simplicity, vaddr == file offset)
    dynstr_addr = dynstr_offset
    # Find and patch the DT_STRTAB entry
    patched_dyn_entries = []
    for entry in dyn_entries:
        tag, val = struct.unpack(endian + "qQ", entry)
        if tag == 5:  # DT_STRTAB
            patched_dyn_entries.append(struct.pack(endian + "qQ", 5, dynstr_addr))
        else:
            patched_dyn_entries.append(entry)
    dynamic = b"".join(patched_dyn_entries)

    # ELF header
    e_ident = b"\x7fELF"
    e_ident += b"\x02"  # 64-bit
    e_ident += b"\x01" if endian == "<" else b"\x02"
    e_ident += b"\x01"  # EV_CURRENT
    e_ident += b"\x00" * 9  # padding

    # 64-bit ELF header after e_ident (48 bytes):
    # e_type(H) e_machine(H) e_version(I) e_entry(Q)
    # e_phoff(Q) e_shoff(Q) e_flags(I) e_ehsize(H)
    # e_phentsize(H) e_phnum(H) e_shentsize(H) e_shnum(H)
    # e_shstrndx(H)
    ehdr = e_ident + struct.pack(
        endian + "HHIQQQIHHHHHH",
        2,  # e_type: ET_EXEC
        62,  # e_machine: EM_X86_64
        1,  # e_version
        0,  # e_entry
        phdrs_offset,  # e_phoff
        shdrs_offset,  # e_shoff
        0,  # e_flags
        ehdr_size,  # e_ehsize
        phdr_size,  # e_phentsize
        num_phdrs,  # e_phnum
        shdr_size,  # e_shentsize
        num_shdrs,  # e_shnum
        0,  # e_shstrndx
    )

    # Program headers
    phdrs = b""
    if interp is not None:
        # PT_INTERP
        phdrs += struct.pack(
            endian + "IIQQQQQQ",
            3,  # p_type: PT_INTERP
            4,  # p_flags: PF_R
            interp_offset,  # p_offset
            interp_offset,  # p_vaddr
            interp_offset,  # p_paddr
            len(interp_bytes),  # p_filesz
            len(interp_bytes),  # p_memsz
            1,  # p_align
        )
    if needed or rpath is not None or runpath is not None:
        # PT_DYNAMIC
        phdrs += struct.pack(
            endian + "IIQQQQQQ",
            2,  # p_type: PT_DYNAMIC
            6,  # p_flags: PF_R|PF_W
            dynamic_offset,  # p_offset
            dynamic_offset,  # p_vaddr
            dynamic_offset,  # p_paddr
            len(dynamic),  # p_filesz
            len(dynamic),  # p_memsz
            8,  # p_align
        )

    # Section headers
    # SHT_NULL (index 0)
    null_shdr = struct.pack(endian + "IIQQQQIIQQ", *([0] * 10))
    # .dynstr (index 1): SHT_STRTAB
    dynstr_shdr = struct.pack(
        endian + "IIQQQQIIQQ",
        0,  # sh_name
        3,  # sh_type: SHT_STRTAB
        0,  # sh_flags
        dynstr_addr,  # sh_addr (== file offset)
        dynstr_offset,  # sh_offset
        len(dynstr),  # sh_size
        0,  # sh_link
        0,  # sh_info
        1,  # sh_addralign
        0,  # sh_entsize
    )
    shdrs = null_shdr + dynstr_shdr

    return ehdr + phdrs + shdrs + interp_bytes + dynamic + dynstr


def _build_elf32(interp=None, needed=None, rpath=None):
    """Build a minimal 32-bit ELF binary."""
    if needed is None:
        needed = []
    endian = "<"

    dynstr = b"\x00"
    needed_offsets = []
    for lib in needed:
        needed_offsets.append(len(dynstr))
        dynstr += lib.encode() + b"\x00"
    rpath_offset = None
    if rpath is not None:
        rpath_offset = len(dynstr)
        dynstr += rpath.encode() + b"\x00"

    dyn_entries = []
    for off in needed_offsets:
        dyn_entries.append(struct.pack(endian + "iI", 1, off))
    if rpath_offset is not None:
        dyn_entries.append(struct.pack(endian + "iI", 15, rpath_offset))
    dyn_entries.append(struct.pack(endian + "iI", 5, 0))  # DT_STRTAB placeholder
    dyn_entries.append(struct.pack(endian + "iI", 0, 0))  # DT_NULL
    dynamic = b"".join(dyn_entries)

    interp_bytes = b""
    if interp is not None:
        interp_bytes = interp.encode() + b"\x00"

    ehdr_size = 52
    phdr_size = 32
    shdr_size = 40

    num_phdrs = 0
    if interp is not None:
        num_phdrs += 1
    if needed or rpath is not None:
        num_phdrs += 1

    num_shdrs = 2

    phdrs_offset = ehdr_size
    shdrs_offset = phdrs_offset + num_phdrs * phdr_size
    interp_offset = shdrs_offset + num_shdrs * shdr_size
    dynamic_offset = interp_offset + len(interp_bytes)
    dynstr_offset = dynamic_offset + len(dynamic)
    dynstr_addr = dynstr_offset

    # Patch DT_STRTAB
    patched = []
    for entry in dyn_entries:
        tag, val = struct.unpack(endian + "iI", entry)
        if tag == 5:
            patched.append(struct.pack(endian + "iI", 5, dynstr_addr))
        else:
            patched.append(entry)
    dynamic = b"".join(patched)

    e_ident = b"\x7fELF\x01\x01\x01" + b"\x00" * 9

    ehdr = e_ident + struct.pack(
        endian + "HHIIIIIHHHHHH",
        2,
        3,
        1,
        0,
        phdrs_offset,
        shdrs_offset,
        0,
        ehdr_size,
        phdr_size,
        num_phdrs,
        shdr_size,
        num_shdrs,
        0,
    )

    phdrs = b""
    if interp is not None:
        phdrs += struct.pack(
            endian + "IIIIIIII",
            3,
            interp_offset,
            interp_offset,
            interp_offset,
            len(interp_bytes),
            len(interp_bytes),
            4,
            1,
        )
    if needed or rpath is not None:
        phdrs += struct.pack(
            endian + "IIIIIIII",
            2,
            dynamic_offset,
            dynamic_offset,
            dynamic_offset,
            len(dynamic),
            len(dynamic),
            6,
            4,
        )

    null_shdr = struct.pack(endian + "IIIIIIIIII", *([0] * 10))
    dynstr_shdr = struct.pack(
        endian + "IIIIIIIIII",
        0,
        3,
        0,
        dynstr_addr,
        dynstr_offset,
        len(dynstr),
        0,
        0,
        1,
        0,
    )
    shdrs = null_shdr + dynstr_shdr

    return ehdr + phdrs + shdrs + interp_bytes + dynamic + dynstr


class TestParseElf(unittest.TestCase):
    def _write_elf(self, data):
        fd, path = tempfile.mkstemp()
        os.write(fd, data)
        os.close(fd)
        self.addCleanup(os.unlink, path)
        return path

    def test_interp(self):
        elf = _build_elf64(
            interp="/lib64/ld-linux-x86-64.so.2",
            needed=["libc.so.6"],
        )
        path = self._write_elf(elf)
        result = patcher.parse_elf(path)
        self.assertIsNotNone(result)
        self.assertEqual(
            result["interp"],
            "/lib64/ld-linux-x86-64.so.2",
        )

    def test_needed(self):
        elf = _build_elf64(
            interp="/lib64/ld-linux-x86-64.so.2",
            needed=["libc.so.6", "libm.so.6", "libdl.so.2"],
        )
        path = self._write_elf(elf)
        result = patcher.parse_elf(path)
        self.assertEqual(
            result["needed"],
            ["libc.so.6", "libm.so.6", "libdl.so.2"],
        )

    def test_rpath(self):
        elf = _build_elf64(
            interp="/lib64/ld-linux-x86-64.so.2",
            needed=["libc.so.6"],
            rpath="/opt/lib:/usr/local/lib",
        )
        path = self._write_elf(elf)
        result = patcher.parse_elf(path)
        self.assertEqual(result["rpath"], "/opt/lib:/usr/local/lib")

    def test_runpath_takes_precedence(self):
        elf = _build_elf64(
            interp="/lib64/ld-linux-x86-64.so.2",
            needed=["libc.so.6"],
            rpath="/old/path",
            runpath="/new/path",
        )
        path = self._write_elf(elf)
        result = patcher.parse_elf(path)
        self.assertEqual(result["rpath"], "/new/path")

    def test_no_interp(self):
        """Shared library without PT_INTERP."""
        elf = _build_elf64(
            interp=None,
            needed=["libc.so.6"],
        )
        path = self._write_elf(elf)
        result = patcher.parse_elf(path)
        self.assertIsNotNone(result)
        self.assertIsNone(result["interp"])

    def test_no_needed(self):
        """Static binary — no DT_NEEDED."""
        elf = _build_elf64(
            interp="/lib64/ld-linux-x86-64.so.2",
        )
        path = self._write_elf(elf)
        result = patcher.parse_elf(path)
        self.assertIsNotNone(result)
        self.assertEqual(result["needed"], [])

    def test_empty_rpath(self):
        elf = _build_elf64(
            interp="/lib64/ld-linux-x86-64.so.2",
            needed=["libc.so.6"],
        )
        path = self._write_elf(elf)
        result = patcher.parse_elf(path)
        self.assertEqual(result["rpath"], "")

    def test_non_elf_file(self):
        path = self._write_elf(b"not an elf file")
        self.assertIsNone(patcher.parse_elf(path))

    def test_truncated_elf(self):
        path = self._write_elf(b"\x7fELF\x02\x01\x01")
        self.assertIsNone(patcher.parse_elf(path))

    def test_nonexistent_file(self):
        self.assertIsNone(patcher.parse_elf("/nonexistent"))

    def test_32bit_elf(self):
        elf = _build_elf32(
            interp="/lib/ld-linux.so.2",
            needed=["libc.so.6"],
            rpath="/opt/lib32",
        )
        path = self._write_elf(elf)
        result = patcher.parse_elf(path)
        self.assertIsNotNone(result)
        self.assertEqual(result["interp"], "/lib/ld-linux.so.2")
        self.assertEqual(result["needed"], ["libc.so.6"])
        self.assertEqual(result["rpath"], "/opt/lib32")

    def test_real_system_binary(self):
        """Test against a real binary if available."""
        for candidate in ["/bin/ls", "/usr/bin/ls"]:
            if os.path.isfile(candidate):
                result = patcher.parse_elf(candidate)
                self.assertIsNotNone(result, f"Failed to parse {candidate}")
                self.assertIsNotNone(result["interp"])
                self.assertIn("libc", str(result["needed"]))
                return
        self.skipTest("No system binary found")


def _place_elf(path, rpath=None):
    """Write a fake ELF binary at *path* and make it executable."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    elf = _build_elf64(
        interp="/lib64/ld-linux-x86-64.so.2",
        needed=["libc.so.6"],
        rpath=rpath or os.path.dirname(path),
    )
    with open(path, "wb") as f:
        f.write(elf)
    os.chmod(path, 0o755)


# Binaries in the real ORFS docker image that docker.BUILD.bazel
# exposes as filegroup srcs.  Paths are relative to the extraction root.
ORFS_BINARIES = [
    "OpenROAD-flow-scripts/tools/install/yosys/bin/yosys",
    "OpenROAD-flow-scripts/tools/install/yosys/bin/yosys-abc",
    "OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad",
    "OpenROAD-flow-scripts/tools/install/OpenROAD/bin/sta",
    "usr/bin/klayout",
]


def _create_fake_orfs_tree(tmpdir):
    """Create a directory tree mirroring the real ORFS docker image layout.

    Returns dict mapping binary name -> absolute path.
    """
    # ld-linux interpreter
    interp_path = os.path.join(tmpdir, "lib64", "ld-linux-x86-64.so.2")
    os.makedirs(os.path.dirname(interp_path), exist_ok=True)
    with open(interp_path, "wb") as f:
        f.write(b"fake-interp")
    os.chmod(interp_path, 0o755)

    bins = {}
    for rel in ORFS_BINARIES:
        abs_path = os.path.join(tmpdir, rel)
        _place_elf(abs_path)
        bins[os.path.basename(rel)] = abs_path

    # yosys share directory with slang plugin
    plugins_dir = os.path.join(
        tmpdir,
        "OpenROAD-flow-scripts",
        "tools",
        "install",
        "yosys",
        "share",
        "yosys",
        "plugins",
    )
    os.makedirs(plugins_dir, exist_ok=True)
    with open(os.path.join(plugins_dir, "slang.so"), "wb") as f:
        f.write(b"fake-slang-plugin")

    return bins


class TestCreateShareSymlinks(unittest.TestCase):
    def test_creates_file_symlinks_for_yosys(self):
        """Per-file symlinks created under share/yosys/ (not a dir symlink)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yosys_share = os.path.join(
                tmpdir, "tools", "install", "yosys", "share", "yosys", "plugins"
            )
            os.makedirs(yosys_share)
            with open(os.path.join(yosys_share, "slang.so"), "w") as f:
                f.write("fake")

            args = argparse.Namespace(directory=tmpdir)
            patcher.create_share_symlinks(args)

            # share/yosys is a real directory (not a symlink)
            top_yosys = os.path.join(tmpdir, "share", "yosys")
            self.assertTrue(os.path.isdir(top_yosys))
            self.assertFalse(os.path.islink(top_yosys))

            # Individual files are symlinks
            slang = os.path.join(top_yosys, "plugins", "slang.so")
            self.assertTrue(os.path.islink(slang))
            self.assertTrue(os.path.isfile(slang))

    def test_skips_libexec(self):
        """Share dirs under libexec/ should not get top-level symlinks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            libexec_share = os.path.join(
                tmpdir, "libexec", "tools", "share", "yosys", "plugins"
            )
            os.makedirs(libexec_share)
            with open(os.path.join(libexec_share, "slang.so"), "w") as f:
                f.write("fake")

            args = argparse.Namespace(directory=tmpdir)
            patcher.create_share_symlinks(args)

            self.assertFalse(
                os.path.exists(os.path.join(tmpdir, "share", "yosys"))
            )

    def test_does_not_overwrite_existing(self):
        """First file found wins; second is ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            first = os.path.join(tmpdir, "first", "share", "yosys")
            os.makedirs(first)
            with open(os.path.join(first, "marker"), "w") as f:
                f.write("first")

            second = os.path.join(tmpdir, "second", "share", "yosys")
            os.makedirs(second)
            with open(os.path.join(second, "marker"), "w") as f:
                f.write("second")

            args = argparse.Namespace(directory=tmpdir)
            patcher.create_share_symlinks(args)

            marker = os.path.join(tmpdir, "share", "yosys", "marker")
            self.assertTrue(os.path.islink(marker))
            self.assertTrue(os.path.isfile(marker))


class TestSetupInterpreter(unittest.TestCase):
    def test_copies_interpreter_to_lib(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            interp_dir = os.path.join(tmpdir, "lib64")
            os.makedirs(interp_dir)
            interp = os.path.join(interp_dir, "ld-linux-x86-64.so.2")
            with open(interp, "wb") as f:
                f.write(b"fake-interp")

            args = argparse.Namespace(directory=tmpdir)
            new_rel = patcher.setup_interpreter(args, "lib64/ld-linux-x86-64.so.2")

            self.assertEqual(new_rel, "_lib/ld-linux-x86-64.so.2")
            new_abs = os.path.join(tmpdir, new_rel)
            self.assertTrue(os.path.isfile(new_abs))
            self.assertTrue(os.access(new_abs, os.X_OK))

    def test_idempotent(self):
        """Calling setup_interpreter twice doesn't fail or change the file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            interp_dir = os.path.join(tmpdir, "lib64")
            os.makedirs(interp_dir)
            interp = os.path.join(interp_dir, "ld-linux-x86-64.so.2")
            with open(interp, "wb") as f:
                f.write(b"fake-interp")

            args = argparse.Namespace(directory=tmpdir)
            rel1 = patcher.setup_interpreter(args, "lib64/ld-linux-x86-64.so.2")
            rel2 = patcher.setup_interpreter(args, "lib64/ld-linux-x86-64.so.2")
            self.assertEqual(rel1, rel2)


class TestGenerateWrapper(unittest.TestCase):
    def test_creates_wrapper_script(self):
        """Wrapper script is created and original ELF moves to libexec/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_dir = os.path.join(tmpdir, "tools", "bin")
            os.makedirs(bin_dir)
            exe = os.path.join(bin_dir, "mytool")
            with open(exe, "wb") as f:
                f.write(b"\x7fELF-fake")
            os.chmod(exe, 0o755)

            args = argparse.Namespace(directory=tmpdir)
            wrapper_info = {
                "root": bin_dir,
                "file": "mytool",
                "interpreter": "_lib/ld-linux-x86-64.so.2",
                "library_paths": ["tools/lib"],
            }
            patcher.generate_wrapper(args, wrapper_info)

            # Wrapper script exists at original path
            self.assertTrue(os.path.isfile(exe))
            with open(exe) as f:
                content = f.read()
            self.assertIn("#!/usr/bin/env bash", content)
            self.assertIn("_lib/ld-linux-x86-64.so.2", content)

            # Original ELF moved to libexec/
            libexec = os.path.join(tmpdir, "libexec", "tools", "bin", "mytool")
            self.assertTrue(os.path.isfile(libexec))
            with open(libexec, "rb") as f:
                self.assertEqual(f.read(), b"\x7fELF-fake")

    def test_wrapper_includes_tcl_library(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_dir = os.path.join(tmpdir, "bin")
            os.makedirs(bin_dir)
            exe = os.path.join(bin_dir, "mytool")
            with open(exe, "wb") as f:
                f.write(b"\x7fELF-fake")

            args = argparse.Namespace(directory=tmpdir)
            wrapper_info = {
                "root": bin_dir,
                "file": "mytool",
                "interpreter": "_lib/ld-linux-x86-64.so.2",
                "library_paths": [],
            }
            patcher.generate_wrapper(args, wrapper_info, tcl_library="usr/share/tcl8.6")

            with open(exe) as f:
                content = f.read()
            self.assertIn("TCL_LIBRARY", content)
            self.assertIn("usr/share/tcl8.6", content)


class TestPatcherIntegration(unittest.TestCase):
    """Integration test: full patcher pipeline on a fake ORFS tree.

    Runs patcher.main() on a directory tree mirroring the real ORFS
    docker image and verifies the resulting structure for all binaries.
    """

    def _run_patcher(self, tmpdir):
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["patcher", tmpdir]
            patcher.main()
        finally:
            sys.argv = old_argv

    def test_all_binaries_wrapped(self):
        """Every ORFS binary is replaced with a wrapper script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bins = _create_fake_orfs_tree(tmpdir)
            self._run_patcher(tmpdir)

            for name, path in bins.items():
                with open(path) as f:
                    content = f.read()
                self.assertIn(
                    "#!/usr/bin/env bash",
                    content,
                    f"{name} was not replaced with a wrapper script",
                )
                self.assertIn("--inhibit-cache", content, f"{name} wrapper malformed")

    def test_all_binaries_moved_to_libexec(self):
        """Original ELFs for all ORFS binaries land in libexec/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bins = _create_fake_orfs_tree(tmpdir)
            self._run_patcher(tmpdir)

            for name, path in bins.items():
                rel = os.path.relpath(path, tmpdir)
                libexec = os.path.join(tmpdir, "libexec", rel)
                self.assertTrue(
                    os.path.isfile(libexec),
                    f"original ELF for {name} not found at {libexec}",
                )

    def test_all_binaries_have_sibling_symlinks(self):
        """_lib/ contains sibling symlinks for every wrapped binary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bins = _create_fake_orfs_tree(tmpdir)
            self._run_patcher(tmpdir)

            for name in bins:
                sibling = os.path.join(tmpdir, "_lib", name)
                self.assertTrue(
                    os.path.islink(sibling),
                    f"_lib/{name} sibling symlink missing",
                )

    def test_interpreter_in_lib(self):
        """_lib/ contains the ld-linux interpreter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_fake_orfs_tree(tmpdir)
            self._run_patcher(tmpdir)

            interp = os.path.join(tmpdir, "_lib", "ld-linux-x86-64.so.2")
            self.assertTrue(os.path.isfile(interp))
            self.assertTrue(os.access(interp, os.X_OK))

    def test_yosys_slang_path_resolves(self):
        """_lib/../share/yosys/plugins/slang.so must resolve.

        This is the path yosys computes via proc_self_dirname() when
        running through the ld-linux wrapper.  If this breaks, yosys
        fails with "cannot open shared object file" at synthesis time.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_fake_orfs_tree(tmpdir)
            self._run_patcher(tmpdir)

            slang_via_lib = os.path.join(
                tmpdir, "_lib", "..", "share", "yosys", "plugins", "slang.so"
            )
            self.assertTrue(
                os.path.isfile(slang_via_lib),
                f"slang.so not reachable at {slang_via_lib} — "
                "yosys will fail to load the slang plugin at runtime",
            )


if __name__ == "__main__":
    unittest.main()
