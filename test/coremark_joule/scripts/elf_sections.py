#!/usr/bin/env python3
"""Read section names and contents from a little-endian 32-bit ELF.

Small enough to avoid putting a cross-toolchain into the data of every
test that wants to look at a section, and it keeps the tests hermetic:
no objdump, no readelf, no dependence on which binutils happens to be
installed.

Only what the study needs: little-endian ELF32 and ELF64, section headers.
"""

import struct

_ELF_MAGIC = b"\x7fELF"
_ELFCLASS32 = 1
_ELFCLASS64 = 2
_ELFDATA2LSB = 1
_SHT_NOBITS = 8


class ElfError(Exception):
    """The file is not an ELF this reader handles."""


def _sections(blob):
    """Yield (name_offset, type, size, offset) per section header.

    Both ELF classes, because the study builds RV32 for three cores and
    RV64 for XiangShan. They differ only in header offsets and in field
    widths; the walk is otherwise identical.
    """
    elf64 = blob[4] == _ELFCLASS64
    if elf64:
        # e_shoff at 0x28, e_shentsize at 0x3a, e_shnum 0x3c, e_shstrndx 0x3e
        (shoff,) = struct.unpack_from("<Q", blob, 0x28)
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", blob, 0x3A)
        off_size = "<QQ"
        off_at = 0x18
    else:
        # e_shoff at 0x20, e_shentsize at 0x2e, e_shnum at 0x30, e_shstrndx 0x32
        (shoff,) = struct.unpack_from("<I", blob, 0x20)
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", blob, 0x2E)
        off_size = "<II"
        off_at = 0x10

    for i in range(shnum):
        base = shoff + i * shentsize
        name_off, sh_type = struct.unpack_from("<II", blob, base)
        sh_offset, sh_size = struct.unpack_from(off_size, blob, base + off_at)
        yield name_off, sh_type, sh_size, sh_offset
    # The string table is itself a section, so it is read by re-walking
    # rather than kept in the loop above.
    base = shoff + shstrndx * shentsize
    str_off, str_size = struct.unpack_from(off_size, blob, base + off_at)
    yield ("strtab", str_off, str_size)


def read_sections(path):
    """Return {section name: bytes}.

    A NOBITS section (.bss) has no file content and maps to b"" -- which
    is the right answer for a comparison, since what it holds at run time
    is decided by crt0, not by the image.
    """
    with open(path, "rb") as f:
        blob = f.read()

    if blob[:4] != _ELF_MAGIC:
        raise ElfError("{}: not an ELF file".format(path))
    if blob[4] not in (_ELFCLASS32, _ELFCLASS64) or blob[5] != _ELFDATA2LSB:
        raise ElfError("{}: only 32-bit little-endian ELF is supported".format(path))

    headers = list(_sections(blob))
    _, str_off, str_size = headers[-1]
    strtab = blob[str_off : str_off + str_size]

    out = {}
    for name_off, sh_type, sh_size, sh_offset in headers[:-1]:
        end = strtab.index(b"\0", name_off)
        name = strtab[name_off:end].decode("ascii")
        if not name:
            continue
        if sh_type == _SHT_NOBITS:
            out[name] = b""
        else:
            out[name] = blob[sh_offset : sh_offset + sh_size]
    return out
