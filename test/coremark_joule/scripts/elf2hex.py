#!/usr/bin/env python3
"""Flatten an ELF into a $readmemh image, one 32-bit word per line.

The harness RAM is a Verilog array loaded by $readmemh from a path given
at run time (+meminit=), which is what lets one simulator binary run both
the two- and three-iteration programs. That matters most for the
gate-level simulators, which are expensive to build and cheap to re-run.

PT_LOAD program headers rather than sections: the segment table is what
says which bytes are loaded and where, and it already accounts for
whatever the linker merged. p_memsz beyond p_filesz is .bss, emitted as
zeros so the image is dense and $readmemh never leaves a word X --
crt0.S zeroes .bss itself, but an X in RAM propagates through a
gate-level netlist long before the first instruction runs.

The *load* address, p_paddr, not the run address p_vaddr. For three of
the study's four cores the two are equal and the distinction never
shows. VeeR is the exception: its data runs in a DCCM inside the
hardened block, which nothing outside can preload, so link_veer.ld
gives those sections a load address in external memory and crt0_veer.S
copies them across. Writing the image at p_vaddr would put them at an
address the memory does not have.

Usage: elf2hex.py <in.elf> <out.hex> [--words N] [--base ADDR]
"""

import argparse
import struct
import sys

_ELF_MAGIC = b"\x7fELF"
_ELFCLASS32 = 1
_ELFCLASS64 = 2
_ELFDATA2LSB = 1
_PT_LOAD = 1


class ElfError(Exception):
    """The file is not an ELF this converter handles."""


def load_segments(blob):
    """Return [(paddr, bytes)] for every PT_LOAD, .bss zero-filled."""
    if blob[:4] != _ELF_MAGIC:
        raise ElfError("not an ELF file")
    if blob[5] != _ELFDATA2LSB:
        raise ElfError("only little-endian ELF is supported")
    if blob[4] not in (_ELFCLASS32, _ELFCLASS64):
        raise ElfError("not a 32- or 64-bit ELF")
    elf64 = blob[4] == _ELFCLASS64

    # The two classes differ in header offsets and in field widths, and in
    # ELF64 p_flags moves ahead of p_offset. Nothing else here cares.
    if elf64:
        (phoff,) = struct.unpack_from("<Q", blob, 0x20)
        phentsize, phnum = struct.unpack_from("<HH", blob, 0x36)
    else:
        (phoff,) = struct.unpack_from("<I", blob, 0x1C)
        phentsize, phnum = struct.unpack_from("<HH", blob, 0x2A)

    out = []
    for i in range(phnum):
        base = phoff + i * phentsize
        if elf64:
            (p_type,) = struct.unpack_from("<I", blob, base)
            p_offset, p_vaddr, p_paddr = struct.unpack_from("<QQQ", blob, base + 0x08)
            p_filesz, p_memsz = struct.unpack_from("<QQ", blob, base + 0x20)
        else:
            p_type, p_offset, p_vaddr = struct.unpack_from("<III", blob, base)
            (p_paddr,) = struct.unpack_from("<I", blob, base + 0x0C)
            p_filesz, p_memsz = struct.unpack_from("<II", blob, base + 0x10)
        if p_type != _PT_LOAD or p_memsz == 0:
            continue
        data = blob[p_offset : p_offset + p_filesz]
        data += b"\0" * (p_memsz - p_filesz)
        out.append((p_paddr, data))
    if not out:
        raise ElfError("no PT_LOAD segments")
    return out


def to_words(segments, words, base=0):
    """Place segments into a flat word image whose first word is `base`.

    Zero is the default because that is where the flat linker script
    puts RAM and where picorv32 and SERV both fetch their first
    instruction. VeeR's and XiangShan's external memory starts at
    0x80000000 instead, so their images are written relative to that.

    A segment outside the array is an error rather than a wrap: silently
    truncating the program would show up as a CRC mismatch much later,
    with nothing pointing back at the image. A segment *below* the base
    is the same kind of error seen from the other side -- usually a
    --base that does not match the linker script.
    """
    image = bytearray(words * 4)
    written = 0
    for paddr, data in segments:
        if paddr < base:
            raise ElfError(
                "segment at 0x{:08x} is below the image base 0x{:08x}; "
                "--base does not match the linker script".format(paddr, base)
            )
        start = paddr - base
        end = start + len(data)
        if end > len(image):
            raise ElfError(
                "segment at 0x{:08x}+{} runs past the {} KiB memory at "
                "0x{:08x}; raise --words or shrink the program".format(
                    paddr, len(data), len(image) // 1024, base
                )
            )
        image[start:end] = data
        written += len(data)
    return image, written


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf")
    parser.add_argument("hex")
    parser.add_argument(
        "--words",
        type=int,
        default=32768,
        help="RAM size in 32-bit words (default 32768, i.e. 128 KiB)",
    )
    parser.add_argument(
        "--base",
        type=lambda v: int(v, 0),
        default=0,
        help="address of the image's first word (default 0). VeeR's "
        "and XiangShan's external memory is at 0x80000000.",
    )
    args = parser.parse_args(argv[1:])

    with open(args.elf, "rb") as f:
        blob = f.read()

    image, written = to_words(load_segments(blob), args.words, args.base)

    with open(args.hex, "w") as f:
        for i in range(0, len(image), 4):
            f.write("{:08x}\n".format(int.from_bytes(image[i : i + 4], "little")))

    print(
        "elf2hex: {} bytes loaded into {} words".format(written, args.words),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
