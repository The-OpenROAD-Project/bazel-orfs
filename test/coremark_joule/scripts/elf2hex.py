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

Usage: elf2hex.py <in.elf> <out.hex> [--words N]
"""

import argparse
import struct
import sys

_ELF_MAGIC = b"\x7fELF"
_ELFCLASS32 = 1
_ELFDATA2LSB = 1
_PT_LOAD = 1


class ElfError(Exception):
    """The file is not an ELF this converter handles."""


def load_segments(blob):
    """Return [(vaddr, bytes)] for every PT_LOAD, .bss zero-filled."""
    if blob[:4] != _ELF_MAGIC:
        raise ElfError("not an ELF file")
    if blob[4] != _ELFCLASS32 or blob[5] != _ELFDATA2LSB:
        raise ElfError("only 32-bit little-endian ELF is supported")

    (phoff,) = struct.unpack_from("<I", blob, 0x1C)
    phentsize, phnum = struct.unpack_from("<HH", blob, 0x2A)

    out = []
    for i in range(phnum):
        base = phoff + i * phentsize
        p_type, p_offset, p_vaddr = struct.unpack_from("<III", blob, base)
        p_filesz, p_memsz = struct.unpack_from("<II", blob, base + 0x10)
        if p_type != _PT_LOAD or p_memsz == 0:
            continue
        data = blob[p_offset : p_offset + p_filesz]
        data += b"\0" * (p_memsz - p_filesz)
        out.append((p_vaddr, data))
    if not out:
        raise ElfError("no PT_LOAD segments")
    return out


def to_words(segments, words):
    """Place segments into a flat word image starting at address 0.

    Address 0 is the base because that is where the linker script puts
    RAM and where picorv32 and SERV both fetch their first instruction.
    A segment outside the array is an error rather than a wrap: silently
    truncating the program would show up as a CRC mismatch much later,
    with nothing pointing back at the image.
    """
    image = bytearray(words * 4)
    written = 0
    for vaddr, data in segments:
        end = vaddr + len(data)
        if end > len(image):
            raise ElfError(
                "segment at 0x{:08x}+{} runs past the {} KiB RAM; raise "
                "--words or shrink the program".format(
                    vaddr, len(data), len(image) // 1024
                )
            )
        image[vaddr:end] = data
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
    args = parser.parse_args(argv[1:])

    with open(args.elf, "rb") as f:
        blob = f.read()

    image, written = to_words(load_segments(blob), args.words)

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
