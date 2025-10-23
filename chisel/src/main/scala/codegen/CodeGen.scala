package codegen

import chisel3._
import circt.stage.ChiselStage
import chisel3.util._


object CodeGen extends App {
  val constructor = Class.forName(args(0)).getConstructors().head
  ChiselStage.emitHWDialect(
    constructor.newInstance().asInstanceOf[chisel3.RawModule],
    Array(),
    args.drop(1)
  )
}
