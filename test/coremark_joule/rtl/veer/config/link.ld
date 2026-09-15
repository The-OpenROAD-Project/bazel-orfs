/*
 NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE
 Generated once from chipsalliance/Cores-VeeR-EH1 at 695883a674c4a59cf96fae874ff4bfac5fecf4e8 (v1.9)

 cmd:    swerv -set reset_vec=0xf0090000 -set=iccm_enable=1 -unset=icache_enable -iccm_region=0xf -iccm_offset=0x90000 -iccm_size=64 -dccm_region=0xf -dccm_offset=0x80000 -dccm_size=64 -btb_size=512 -bht_size=2048 -ahb_lite -set=fpga_optimize=0 -snapshot=cmj 

*/

OUTPUT_ARCH( "riscv" )
ENTRY(_start)

SECTIONS
{
  . = 0xf0090000;
  .text.init .  : { *(.text.init) }
   . = 0xf0090000 ;
  .text . : { *(.text) }
  _end = .;
  . = 0xe0580000;
  .data.io .  : { *(.data.io) }
    . = 0xf0080000 ;
  .data  :  ALIGN(0x800) { *(.*data) *(.rodata*)}
  .bss :  {BSS_START = .; *(.*bss)}
  BSS_END = .;
  STACK = ALIGN(16) + 0x1000;
    . = 0xfffffff0; .iccm.ctl . : { LONG(0xf0090000); LONG(0xf009ffff) }
    . = 0xfffffff8; .data.ctl : { LONG(0xf0080000); LONG(STACK) }
}

