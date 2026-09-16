/*
 NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE
 Generated once from chipsalliance/Cores-VeeR-EH1 at 695883a674c4a59cf96fae874ff4bfac5fecf4e8 (v1.9)

 cmd:    swerv -set=icache_enable=1 -icache_size=16 -unset=iccm_enable -dccm_region=0xf -dccm_offset=0x80000 -dccm_size=64 -btb_size=512 -bht_size=2048 -ahb_lite -set=fpga_optimize=0 -snapshot=cmj 

*/

OUTPUT_ARCH( "riscv" )
ENTRY(_start)

SECTIONS
{
  . = 0x80000000;
  .text.init .  : { *(.text.init) }
  
  .text . : { *(.text) }
  _end = .;
  . = 0xd0580000;
  .data.io .  : { *(.data.io) }
    . = 0xf0080000 ;
  .data  :  ALIGN(0x800) { *(.*data) *(.rodata*)}
  .bss :  {BSS_START = .; *(.*bss)}
  BSS_END = .;
  STACK = ALIGN(16) + 0x1000;
  
    . = 0xfffffff8; .data.ctl : { LONG(0xf0080000); LONG(STACK) }
}

