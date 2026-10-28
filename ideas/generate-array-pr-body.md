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
| LoadQueueReplay | 28.9 | ~15 ¹ | 1,670.7 |
| PhysicalStoreQueue | 27.2 ² | 21.2 | 1,519.5 |
| VirtualStoreQueue | 6.6 | ≤ 3 ³ | 1,298.6 |
| LoadQueueRAR | 4.5 | ≤ 3 ³ | 1,172.6 |
| TLBFA / TLBFA_1 | | ≤ 3 ³ | 435.1 / 507.2 |

¹ Side by side with PhysicalStoreQueue. ² The decode_once flow, not the
carve. ³ Four blocks side by side in 172 s.

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
  run both for each block.

### Not covered yet

- The read side: PhysicalStoreQueue's forwarding compares every entry
  and reduces across them; its top still synthesises for 978 s.
- Threshold compares (x >= K): VirtualLoadQueue.
- Bpu and VecRegionModule gain from the flow knobs alone (39 min side by
  side against 41.2 and 49.0) but miss 2,000 ps with setup repair off.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
