# generate_array: the PR #1419 body, drafted

Status: **draft, not posted.** The body below is for the human to post to
#1419 when they choose; nothing here has left this machine.

---

## XiangShan's arrays found, extracted and proven, without per-design code

The blocks the XSTile carve hardens hold arrays the RTL never wrote as
arrays: the Rob's 352 entries, the load and store queues, the TLB's
entries. `test/coremark_joule/designs/asap7/xiangshan/arrays` finds them
in a block's own RTL, writes each as one cell instanced per entry, decodes
the index comparisons once in the parent, and proves the result equal to
the RTL.

### Build time to global route

| Block | Carve (min) | Extracted (min) | Period (ps) |
| --- | ---: | ---: | ---: |
| Rob | 73.5 | 23.5 | 1,913.9 |
| LoadQueueReplay | 28.9 | ~9.5 | 1,469.7 |
| PhysicalStoreQueue | 27.2 ¹ | 8.6 | 1,905.1 |
| VirtualStoreQueue | 6.6 | ≤ 6 ² | 1,485.0 |
| LoadQueueRAR | 4.5 | ≤ 6 ² | 997.7 |
| TLBFA / TLBFA_1 | | ≤ 6 ² | 285.9 / 349.5 |

¹ The decode_once flow, not the carve. ² Four blocks side by side.

Every period is inside XSTile's ~2,000 ps. The flows skip setup repair
at and after CTS, floorplan's repair, and pin access; global route is
route-0. The surgered Rob with the hand-written generator
(`rob_array:Rob`) takes ~33 min to 1,712.8 ps; the generic one
(`rob_array:RobEntries`) differs from it only in the netlist.

### How

- `proc_json.py`: the block after yosys's `proc`, as JSON.
- `entries.py`: entries are word *i* of arrays of equal length; each
  entry's cone is a structural signature with constants, shared-bit
  references and x == K / x != K comparisons decided across entries (the
  same, affine in the entry, or in its bank). Duplicate cells are merged,
  private port buffers seen through, and arrays that differ between
  entries left inline.
- `extract.py`: the template entry as `<Module>Entry`, instanced per
  entry; each index comparison decoded once per distinct operand (one per
  bank for a bank's pointer).
- `check.py`: registers and blackboxes as cut points, a yosys miter, ABC
  `iprove`, and a negative control (one register's D-mux swapped) that
  must come out different. `<top>_check_test` and `<top>_control_test`
  run both for each block. The Rob's decoded form, 80 comparisons in
  eight per-bank decoders, proves in 97 min; the others in seconds to
  minutes.

### Not covered yet

- The read side where entries' read cones differ (LoadQueueRAW,
  LoadQueueRAR); where they agree it is in the cell (PhysicalStoreQueue's
  top synthesis 978 s to 137 s).
- Threshold compares (x >= K): VirtualLoadQueue.
- Bpu and VecRegionModule gain from the flow knobs alone (39 min side by
  side against 41.2 and 49.0) but miss 2,000 ps with setup repair off.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
