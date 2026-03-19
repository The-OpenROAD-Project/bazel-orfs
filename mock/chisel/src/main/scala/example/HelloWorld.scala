package example

import chisel3._

class HelloWorld extends Module {
  val io = IO(new Bundle {
    val led = Output(Bool())
  })

  val counter = RegInit(0.U(24.W))
  counter := counter + 1.U
  io.led := counter(23)
}
