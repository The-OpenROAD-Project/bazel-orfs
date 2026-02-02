from os import path
import sys
import logging
from najaeda import netlist
import yaml

logging.basicConfig(level=logging.INFO)

vars_files = sys.argv[1]
cleaned_netlist = sys.argv[2]
dirty_netlists = sys.argv[3:]

with open(vars_files, 'r') as f:
    vars = yaml.safe_load(f)

lib_files = vars["LIB_FILES"].split(' ')

# naja will read lib.gz files in the future, for now...
ungzipped_libs = []
for lib_file in lib_files:
    if lib_file.endswith('.gz'):
        import gzip
        import shutil
        ungzipped_file = lib_file[:-3]
        with gzip.open(lib_file, 'rb') as f_in:
            with open(ungzipped_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        ungzipped_libs.append(ungzipped_file)
    else:
        ungzipped_libs.append(lib_file)
lib_files = ungzipped_libs

netlist.load_liberty(lib_files)
top = netlist.load_verilog(dirty_netlists)
netlist.apply_constant_propagation()
netlist.apply_dle()
top.dump_verilog(cleaned_netlist)
