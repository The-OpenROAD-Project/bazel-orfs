"""XiangShan's 352 RobEntryCells as one structural asap7 netlist,
RobEntryArray: the same state and update rules, every channel decoded once
and shared by all entries.

RobEntryCell (patches 0003, 0007, 0008 on XiangShan aa6b5203) reads one
1,219-bit bus every cell shares, robEntryCellInBits, and compares its
constant index, io_idx, against every channel in it. The fields of that
bus, as firtool lays them out, are below (_IN); rob_surgery.py checks
that RobEntryCell is the text this was written from before it swaps the
cells for the array.

    rob_array_gen.py <out.v> [entries]
"""

import math
import sys

from rob_gen import Net, _bus

ENTRIES = 352
IN_BITS = 1219
ENTRY_BITS = 31

IDX = 9
ENQ = 8
ENQ_STRIDE = 34
COMMIT = 8
EXU_WB = 29
EXC_WB = 13
FFLAGS_WB = 7
VXSAT_WB = 4
BRANCH_WB = 3


def _in(lo, w=1):
    """io_in[lo +: w], LSB first."""
    return [f"io_in[{lo + k}]" for k in range(w)]


def _enq(k):
    b = ENQ_STRIDE * k
    return {
        "ilastsize": _in(947 + b)[0],
        "iretire": _in(948 + b, 6),
        "itype": _in(954 + b, 4),
        "needFlush": _in(958 + b)[0],
        "vls": _in(959 + b)[0],
        "numWB": _in(960 + b, 5),
        "rf": _in(969 + b)[0],
        "robIdx": _in(970 + b, IDX),
        "first": _in(979 + b)[0],
        "valid": _in(980 + b)[0],
        "alloc": _in(874 + IDX * k, IDX),
        "allowInterrupt": _in(866 + k)[0],
    }


CAN_ACCEPT = _in(946)[0]
REDIRECT_VALID = _in(865)[0]
REDIRECT_VALID_REG = _in(864)[0]
REDIRECT_ALL = _in(845)[0]
REDIRECT_BEGIN = _in(855, IDX)
REDIRECT_END = _in(846, IDX)
IS_COMMIT = _in(844)[0]


def generate(n=ENTRIES):
    net = Net()
    a = IDX

    def dec(idx, en):
        return net.decode(idx, n, en)

    enq = [_enq(k) for k in range(ENQ)]
    # enqOH_k: valid, firstUop and canAccept, at the allocate pointer
    alloc = [
        dec(e["alloc"], net.and2(net.and2(e["valid"], e["first"]), CAN_ACCEPT))
        for e in enq
    ]
    # uopCanEnq_k: valid and canAccept, at the uop's robIdx
    uop = [dec(e["robIdx"], net.and2(e["valid"], CAN_ACCEPT)) for e in enq]
    commit = [
        dec(_in(764 + IDX * c, IDX), net.and2(IS_COMMIT, _in(836 + c)[0]))
        for c in range(COMMIT)
    ]
    exu = [dec(_in(474 + 10 * j, IDX), _in(483 + 10 * j)[0]) for j in range(EXU_WB)]
    exu_cnt = [_in(329 + 5 * j, 5) for j in range(EXU_WB)]
    exc = [
        dec(_in(199 + 10 * j, IDX), net.and2(_in(208 + 10 * j)[0], _in(186 + j)[0]))
        for j in range(EXC_WB)
    ]
    ff = [
        dec(_in(80 + 16 * j, IDX), net.and2(_in(89 + 16 * j)[0], _in(79 + 16 * j)[0]))
        for j in range(FFLAGS_WB)
    ]
    ff_flags = [_in(74 + 16 * j, 5) for j in range(FFLAGS_WB)]
    vx = [
        dec(_in(31 + 11 * j, IDX), net.and2(_in(40 + 11 * j)[0], _in(30 + 11 * j)[0]))
        for j in range(VXSAT_WB)
    ]
    br = [dec(_in(10 * j, IDX), _in(9 + 10 * j)[0]) for j in range(BRANCH_WB)]

    # the redirect's range: idx > begin and idx < end, wrapping
    end_gt_begin = net.gt(REDIRECT_END, REDIRECT_BEGIN)
    gt_b = net.thermo(REDIRECT_BEGIN, n, greater=True)
    lt_e = net.thermo(REDIRECT_END, n, greater=False)
    no_redirect = net.inv(REDIRECT_VALID)
    reset_n = net.inv("reset")

    for i in range(n):
        net.tag = f"e{i}"
        # registers, LSB first; each flop's QN is its value
        d, q = {}, {}
        for name, w in (
            ("needFlush", 1),
            ("uopNum", 5),
            ("realDestSize", 4),
            ("vxsat", 1),
            ("fflags", 5),
            ("valid", 1),
            ("ilastsize", 1),
            ("iretire", 6),
            ("itype", 4),
            ("interrupt_safe", 1),
            ("vls", 1),
        ):
            d[name] = [net.wire() for _ in range(w)]
            if name == "valid":
                # the one register with a reset, asynchronous, to zero:
                # QN is the value, so reset sets the flop
                q[name] = [
                    net.cell(
                        "DFFASRHQNx1",
                        outs=("QN",),
                        CLK="clock",
                        D=d[name][0],
                        SETN=reset_n,
                        RESETN=net.one,
                    )
                ]
            else:
                q[name] = [net.ff_n(x) for x in d[name]]

        def assign_d(name, k, nxt):
            net.assign(d[name][k], net.negate(nxt))

        valid = q["valid"][0]
        enq_oh = [alloc[k][i] for k in range(ENQ)]
        enq_hit = net.or_tree(enq_oh)
        gen = net.and2(enq_hit, no_redirect)
        uop_hit = [uop[k][i] for k in range(ENQ)]
        inst_hit = [net.and2(uop_hit[k], enq[k]["first"]) for k in range(ENQ)]
        inst_any = net.or_tree(inst_hit)
        uop_any = net.or_tree(uop_hit)
        first_enq = net.and2(net.inv(valid), inst_any)

        def mux1h(field, w):
            words = [[enq[k][field]] if w == 1 else enq[k][field] for k in range(ENQ)]
            return net.and_or(enq_oh, words)

        # vls and interrupt_safe: written on any enqueue hit
        for name, field in (("vls", "vls"), ("interrupt_safe", "allowInterrupt")):
            v = mux1h(field, 1)[0]
            assign_d(name, 0, net.mux(enq_hit, q[name][0], v))

        # itype: set to taken (5) by a branch, else written on enqueue
        it = q["itype"]
        taken = net.or_tree([br[j][i] for j in range(BRANCH_WB)])
        settaken = net.and2(net.and2(valid, net.eq_const(it, 4)), taken)
        enq_itype = mux1h("itype", 4)
        for k in range(4):
            v = net.mux(gen, it[k], enq_itype[k])
            assign_d(
                "itype", k, net.mux(settaken, v, net.one if 5 >> k & 1 else net.zero)
            )
        for name, w in (("iretire", 6), ("ilastsize", 1)):
            vals = mux1h(name, w)
            for k in range(w):
                assign_d(name, k, net.mux(gen, q[name][k], vals[k]))

        # fflags and vxsat: OR-accumulated, cleared on the first enqueue
        ffres = net.and_or([ff[j][i] for j in range(FFLAGS_WB)], ff_flags)
        for k in range(5):
            v = net.or2(q["fflags"][k], ffres[k])
            assign_d("fflags", k, net.and2(net.inv(first_enq), v))
        vxres = net.or_tree([vx[j][i] for j in range(VXSAT_WB)])
        assign_d(
            "vxsat", 0, net.and2(net.inv(first_enq), net.or2(vxres, q["vxsat"][0]))
        )

        # realDestSize: the count of register-writing uops enqueued
        uop_rf = [net.and2(uop_hit[k], enq[k]["rf"]) for k in range(ENQ)]
        dest = _popcount(net, uop_rf, 4)
        rds = q["realDestSize"]
        acc = net.add(rds, dest)
        upd = net.and2(valid, uop_any)
        for k in range(4):
            v = net.mux(upd, rds[k], acc[k])
            assign_d("realDestSize", k, net.mux(first_enq, v, dest[k]))

        # uopNum: loaded on the first enqueue (lowest port first), counted
        # down by the writeback that hits the entry
        prio, seen = [], net.zero
        for k in range(ENQ):
            prio.append(net.and2(inst_hit[k], net.inv(seen)) if k else inst_hit[k])
            seen = net.or2(seen, inst_hit[k])
        # PriorityMux: the last port is the default when none of the others hit
        prio[-1] = net.inv(net.or_tree(inst_hit[:-1]))
        num = net.and_or(prio, [enq[k]["numWB"] for k in range(ENQ)])
        wbcnt = net.and_or([exu[j][i] for j in range(EXU_WB)], exu_cnt)
        un = q["uopNum"]
        down = net.sub(un, wbcnt)
        for k in range(5):
            v = net.mux(valid, net.mux(inst_any, un[k], num[k]), down[k])
            assign_d("uopNum", k, v)

        # needFlush: sticky while valid, written on enqueue otherwise
        nfwb = net.or_tree([exc[j][i] for j in range(EXC_WB)])
        nf = q["needFlush"][0]
        enq_nf = mux1h("needFlush", 1)[0]
        v = net.mux(valid, net.mux(gen, nf, enq_nf), net.or2(nf, nfwb))
        assign_d("needFlush", 0, v)

        # valid: cleared by commit, set by enqueue, cleared by the redirect
        commit_cond = net.or_tree([commit[c][i] for c in range(COMMIT)])
        in_range = net.mux(
            end_gt_begin, net.or2(gt_b[i], lt_e[i]), net.and2(gt_b[i], lt_e[i])
        )
        flush = net.and2(REDIRECT_VALID_REG, net.or2(in_range, REDIRECT_ALL))
        nvalid = net.and2(
            net.inv(commit_cond), net.or2(gen, net.and2(net.inv(flush), valid))
        )
        assign_d("valid", 0, nvalid)

        # io_entry, MSB first: vls, interrupt_safe, itype, iretire,
        # ilastsize, valid, fflags, 0, vxsat, realDestSize, uopNum, needFlush
        bits = (
            q["needFlush"]
            + q["uopNum"]
            + q["realDestSize"]
            + q["vxsat"]
            + [net.zero]
            + q["fflags"]
            + q["valid"]
            + q["ilastsize"]
            + q["iretire"]
            + q["itype"]
            + q["interrupt_safe"]
            + q["vls"]
        )
        assert len(bits) == ENTRY_BITS
        for k, v in enumerate(bits):
            net.assign(f"io_entries[{i * ENTRY_BITS + k}]", v)
    # no buffer trees and no sizing: the flow buffers to its
    # set_max_fanout and sizes, which beat building them here on the toy
    return net


def _popcount(net, bits, width):
    """Column sums of full adders, width bits out."""
    cols = [list(bits)] + [[] for _ in range(width)]
    out = []
    for k in range(width):
        col = cols[k]
        while len(col) > 2:
            x, y, z = col.pop(), col.pop(), col.pop()
            t = net.xor2(x, y)
            col.insert(0, net.xor2(t, z))
            cols[k + 1].append(net.or2(net.and2(x, y), net.and2(t, z)))
        if len(col) == 2:
            x, y = col
            col[:] = [net.xor2(x, y)]
            cols[k + 1].append(net.and2(x, y))
        out.append(col[0] if col else net.zero)
    return out


def main(argv):
    out = argv[1]
    n = int(argv[2]) if len(argv) > 2 else ENTRIES
    net = generate(n)
    ports = [
        "input clock",
        "input reset",
        f"input [{IN_BITS - 1}:0] io_in",
        f"output [{n * ENTRY_BITS - 1}:0] io_entries",
    ]
    with open(out, "w") as f:
        f.write(
            "\n".join(
                ["module RobEntryArray("]
                + [",\n".join("  " + p for p in ports), ");"]
                + net.verilog()
                + ["endmodule", ""]
            )
        )


if __name__ == "__main__":
    main(sys.argv)
