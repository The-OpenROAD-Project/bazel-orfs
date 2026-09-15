/*
 NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE NOTE
 Generated once from chipsalliance/Cores-VeeR-EH1 at 695883a674c4a59cf96fae874ff4bfac5fecf4e8 (v1.9)

 cmd:    swerv -target=default_ahb -set=fpga_optimize=0 -snapshot=cmj 

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
    . = 0xf0040000 ;
  .data  :  ALIGN(0x800) { *(.*data) *(.rodata*)}
  .bss :  {BSS_START = .; *(.*bss)}
  BSS_END = .;
  STACK = ALIGN(16) + 0x1000;
  
    . = 0xfffffff8; .data.ctl : { LONG(0xf0040000); LONG(STACK) }
}

