# Arrays in more than one register placement, the context picks

Status: **proposed, not built.** The literature is read (below). Nothing is measured yet beyond the ohsched baseline that prompted the idea.

## Problem

A generated array fixes where its registers sit. generate_ram registers the address and the write side, and its read is combinational to the output. yosys's flops have no fixed placement: with `SYNTH_RETIME_MODULES`, synthesis moves them through the logic around them.

The ohsched toy (`test/array_toys`, 32 × 32, `lanes`) shows the cost. The generated arm's worst path runs from the read address register through the decoder (three AND2 levels, about 95 ps), the five-level read tree and the compare. That is 335 ps, against yosys's 299 ps register to register.

Retiming did reach into the array: the pick registers ended up past the one-hot-to-binary encode, as `arr.ram.addr_r1`. But that move only shifts logic in front of the array. The decode and read tree stay behind the address register, so a placement with the register later on the read side was never tried.

## Idea

Have generate_array and generate_ram emit each array in more than one register placement, all with the same cycle-level function. Build each array instance the way that suits the logic around it.

| Version | Read side | Suits |
|---|---|---|
| A (today) | Register on the read address; decode and read tree in the next cycle | A deep address cone and a shallow consumer |
| B | Address straight into the decoder; register on the read data, after the read tree | A shallow address cone (a pick register right on the address) and a deep consumer (ohsched's compare) |

On the write side the choice is the same: register the write data and enable, or let the write path end at the storage cell. A latch storage cell can then borrow time.

**A and B differ in function when a port reads the word written in the same cycle.**
- A reads after that cycle's write.
- B captures the data before it.

B therefore needs a bypass mux (write data forwarded when the addresses match) to keep the function. That mux costs time and area, and it is part of B's price. When the RTL never reads a word in the cycle it is written, B needs no bypass. That is a property the front end can check.

The FPGA vendors expose the same choice as read-during-write modes. A version that changes the latency changes the function and is not on the menu: no register is added.

**Ways to pick:**
1. **Per flow, as an A/B.** Two variants of the flow, the grt period decides. This is how the arrays are compared today, and it is enough for the toys and the blocks.
2. **Per instance, at synthesis.** Each version as a timing model. The slack at the array's pins in its context (arrival at the address, required time at the read data) names the version, the way datapath generators pick an adder or multiplier architecture from arrival times and output constraints.
3. **Let retiming pick.** Flatten the generated periphery (decoders, read tree, write muxes) into the retiming scope, so the min-period retiming moves the register itself. This is the boundary lever G3 already measures (generate_ram's `periphery verilog` option). If G3 closes the gap, versions A and B are only the storage-cell boundary and the bypass, and route 3 is the general one.

## Literature

- **Retiming itself.**
  - [Leiserson and Saxe, "Retiming synchronous circuitry", Algorithmica 6, 1991](https://link.springer.com/article/10.1007/BF01759032): registers relocated with the behaviour unchanged, a polynomial algorithm for minimum period, and minimum-register retiming.
  - [Hurst, Mishchenko and Brayton, "Fast minimum-register retiming via binary maximum-flow", FMCAD 2007](https://people.eecs.berkeley.edu/~alanmi/publications/2007/tech07_ret.pdf): the max-flow formulation behind ABC's retiming.
  - A memory is a boundary there: its storage is state no retiming moves. Only the registers at its ports can move, which is what the versions above enumerate.
- **FPGA memory blocks.** Block RAMs have registered inputs and optional output registers, a fixed menu of exactly this choice. Tools pull a register at a block's input or output into it.
  - [Intel embedded memory user guide](https://people.ece.cornell.edu/land/courses/ece5760/DE1_SOC/ug_ram_rom.pdf): registered inputs, optional output registers, read-during-write modes.
  - [AMD forum on register pull-in](https://adaptivesupport.amd.com/s/question/0D52E00006hphSlSAI/register-retiming?language=en_US): a forum post, not a reference.
  - [Intel Hyperflex handbook](https://cdrdv2-public.intel.com/704787/s10_hp_hb-20-1-683353-704787.pdf): its retiming restrictions list what blocks a register move; RAM inputs carry bypassable registers.
- **Choosing an implementation by context.** [Zimmermann, "Datapath synthesis for standard-cell design"](https://iis-people.ee.ethz.ch/~zimmi/publications/datapath_synthesis.pdf): context-driven generators pick a datapath architecture from input arrival times and output constraints. Route 2 is the same idea, applied to where an array's registers sit.

## Impact

Not measured. On ohsched `lanes` the read side sets the period, and version B would move the about 95 ps of decode into the pick cycle. Whether that cycle has the slack is the first measurement. On `fill` the worst path is the write side (the OR of 8 port enables, then the hold mux), so B alone would not help there; the write-side version or the bank write (G4) would.

## Effort

Medium.
- A read-data-register option in generate_ram (OpenROAD `src/ram`), carried as a patch, with a bypass when the spec says a port can read the word written in the same cycle.
- The same in structgen's parts.
- A flow variant per version on the toys, checked against the yosys arm in the existing co-simulation, plus a negative control with the bypass removed.
- Route 2 (per-instance pick from slack) is larger and waits until routes 1 and 3 have shown how much is on the table.
