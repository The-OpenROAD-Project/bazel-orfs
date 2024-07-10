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
            link = os.path.join(root, file)
            if os.path.islink(link) and os.path.isabs(os.readlink(link)):
                target = os.path.join(args.directory, os.readlink(link))
                link_to_target = os.path.relpath(target, start=root)
                os.unlink(link)
                os.symlink(link_to_target, link)
                continue

            if magic(os.path.join(root, file)) != ELF_MAGIC:
                continue

            needed_result = subprocess.run([args.patchelf, '--print-needed', file], cwd=root, capture_output=True)
            needed_libs = needed_result.stdout.decode('utf-8').strip()
            if not needed_libs:
                continue

            rpath_fragments = subprocess.check_output([args.patchelf, '--print-rpath', file], cwd=root).decode('utf-8').strip()
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
            subprocess.check_call([args.patchelf, '--force-rpath', '--set-rpath', rpath, '--no-default-lib', file], cwd=root)

            interpreter_result = subprocess.run([args.patchelf, '--print-interpreter', file], cwd=root, capture_output=True)
            if interpreter_result.returncode != 0:
                continue

            interpreter_old = interpreter_result.stdout.decode('utf-8').strip()
            execution_root = os.path.normpath(os.path.join(args.directory, '..', '..'))
            interp = os.path.relpath(interpreter_old, start = '/')
            execution_root_to_interp = os.path.relpath(os.path.join(args.directory, interp), execution_root)
            subprocess.check_call([args.patchelf, '--set-interpreter', execution_root_to_interp, file], cwd=root)




if __name__ == '__main__':
    main()
