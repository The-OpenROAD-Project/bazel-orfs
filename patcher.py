#! /usr/bin/env python3

import argparse
import os
import subprocess

DEFAULT_SEARCH_PATHS = [
    '/lib64',
    '/usr/lib/x86_64-linux-gnu',
]

ELF_MAGIC = b'\x7fELF'

def magic(path):
    if not os.path.isfile(path):
        return None

    with open(path, 'rb') as f:
        return f.read(len(ELF_MAGIC))

    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', help='Directory to patch.')
    parser.add_argument('-p', '--patchelf', default = 'patchelf', help='`patchelf` binary to use.')
    args = parser.parse_args()

    for root, dirs, files in os.walk(args.directory):
        for file in files:
            if magic(os.path.join(root, file)) != ELF_MAGIC:
                continue

            info_result = subprocess.run([args.patchelf, '--print-interpreter', '--print-rpath', file], cwd=root, capture_output=True)
            if info_result.returncode != 0:
                continue

            interpreter_old, rpath_fragments, _ = info_result.stdout.decode('utf-8').split('\n')

            rpaths = []
            for rpath in rpath_fragments.split(':') + DEFAULT_SEARCH_PATHS:
                if not rpath:
                    continue

                if '$ORIGIN' in rpath:
                    rpaths.append(rpath)
                else:
                    elf = os.path.join('/', os.path.relpath(root, start=args.directory))
                    elf_to_rpath = os.path.relpath(rpath, start=elf)
                    rpaths.append(os.path.join('$ORIGIN', elf_to_rpath))
            rpath = ":".join(rpaths).encode('utf-8')
            interpreter = os.path.join(args.directory, os.path.relpath(interpreter_old, start = '/'))
            subprocess.check_output([args.patchelf, '--force-rpath', '--set-rpath', rpath, '--no-default-lib', file], cwd=root)
            subprocess.check_output([args.patchelf, '--set-interpreter', interpreter, file], cwd=root)



if __name__ == '__main__':
    main()
