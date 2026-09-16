/* VeeR's clock gate, mapped onto ASAP7's integrated clock gate.
 *
 * beh_lib.sv defines the gate itself -- a transparent latch on the low
 * phase of CP, ANDed with CP -- and names it by the `TEC_RV_ICG macro,
 * which this configuration sets to `clockhdr`. The macro names both the
 * definition and the instantiation, so the module cannot be redirected
 * from the outside: whatever name it carries, beh_lib.sv defines it.
 * Substituting it after elaboration is the only way to get a real cell
 * without editing VeeR. cmj_veer_icg.ys is what applies this template,
 * and carries the two reasons it cannot be applied more simply: synth's
 * own -extra-map runs after flatten, by which point every clockhdr
 * instance has been inlined; and the slang frontend gives each instance
 * its own module name, so the cells must be folded back onto this one
 * with chtype before techmap can see them.
 *
 * Why it matters is timing rather than area. A transparent latch lets
 * OpenSTA borrow time across it, so a reg-to-reg path through a gated
 * clock reports slack that a flop-based path would not -- which is why
 * VeeR's reg2reg WNS came out at exactly zero on eight paths at once
 * and why section 8.3 cannot push this core to its own f_max. An ICG is
 * a cell, not a borrowable latch, and the analysis becomes the same
 * question the other three cores answer.
 *
 * Ports are VeeR's, body is ASAP7's: TE is the scan enable, E the
 * enable, CP the clock and Q the gated clock.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
module clockhdr (
	input  wire TE,
	input  wire E,
	input  wire CP,
	output wire Q
);
	ICGx1_ASAP7_75t_R latch (
		.CLK (CP),
		.ENA (E),
		.SE  (TE),
		.GCLK(Q)
	);
endmodule
