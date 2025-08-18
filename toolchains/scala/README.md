# Scala toolchain to work with Chisel

This toolchain is adapted to work with Chisel and support vscode with bloop.

One of the problem with bazelbsp is that it invokes bazel, which locks up the GUI as well as the command line.

bloop on the other hand runs completely independently of Bazel inside vscode

## Setting up example

See ./BUILD.bazel for an example on how to set up `scala_bloop`.

    NOTE! This will erase any existing .metals, .bloop and .bazelbsp folders in the project.

Set up bloop files, stop vscode, re-run every time you add and remove a file from the project:

    bazelisk run :bloop

Now run vscode:

    code .

Open Example.scala, start the Metals doctor to verify that "blooplib" is hooked up and working without any serious warnings.

You should now have Scala tooltips, references, etc. for your project.

## Metals doctor healthy example

![alt text](metals-doctor.png)

## Intellisense example

![alt text](intellisense.png)
