/* orfsfork: raw POSIX primitives for the fork/join snapshot idiom in
 * fork.tcl. Compiled with USE_TCL_STUBS so the one .so loads into any host
 * embedding the same-major Tcl — including a statically linked OpenROAD,
 * which exports no Tcl_* symbols (Tcl_InitStubs resolves the stub table
 * through the interp pointer, not the dynamic linker).
 */
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include <tcl.h>

static int
PosixForkCmd(void *cd, Tcl_Interp *interp, int objc, Tcl_Obj *const objv[])
{
  (void) cd;
  if (objc != 1) {
    Tcl_WrongNumArgs(interp, 1, objv, NULL);
    return TCL_ERROR;
  }
  /* Buffered stdio would be duplicated into the child and flushed twice. */
  fflush(NULL);
  pid_t pid = fork();
  if (pid < 0) {
    Tcl_SetObjResult(interp,
                     Tcl_ObjPrintf("fork failed: %s", strerror(errno)));
    return TCL_ERROR;
  }
  Tcl_SetObjResult(interp, Tcl_NewWideIntObj((Tcl_WideInt) pid));
  return TCL_OK;
}

/* posix_waitpid pid -> exit status: N for exit(N), 128+SIG for a signal
 * (142 = SIGALRM = a posix_alarm deadline fired), 255 for anything else. */
static int
PosixWaitpidCmd(void *cd, Tcl_Interp *interp, int objc, Tcl_Obj *const objv[])
{
  (void) cd;
  if (objc != 2) {
    Tcl_WrongNumArgs(interp, 1, objv, "pid");
    return TCL_ERROR;
  }
  Tcl_WideInt pid;
  if (Tcl_GetWideIntFromObj(interp, objv[1], &pid) != TCL_OK) {
    return TCL_ERROR;
  }
  int raw = 0;
  pid_t reaped;
  do {
    reaped = waitpid((pid_t) pid, &raw, 0);
  } while (reaped < 0 && errno == EINTR);
  if (reaped < 0) {
    Tcl_SetObjResult(interp,
                     Tcl_ObjPrintf("waitpid failed: %s", strerror(errno)));
    return TCL_ERROR;
  }
  int status = 255;
  if (WIFEXITED(raw)) {
    status = WEXITSTATUS(raw);
  } else if (WIFSIGNALED(raw)) {
    status = 128 + WTERMSIG(raw);
  }
  Tcl_SetObjResult(interp, Tcl_NewIntObj(status));
  return TCL_OK;
}

/* posix_alarm seconds: self-destruct deadline via alarm(2)/SIGALRM.
 *
 * Timeouts are enforced in the CHILD, not by the parent killing it: a
 * kill from outside reaps only the direct child and orphans its running
 * descendants, which then hold the machine and the stdout pipe open
 * indefinitely. A deadline armed inside every forked process bounds the
 * whole tree -- no orphan can outlive its own alarm. Deadlines do not
 * survive fork, so each generation re-arms its own (fork.tcl -timeout). */
static int
PosixAlarmCmd(void *cd, Tcl_Interp *interp, int objc, Tcl_Obj *const objv[])
{
  (void) cd;
  if (objc != 2) {
    Tcl_WrongNumArgs(interp, 1, objv, "seconds");
    return TCL_ERROR;
  }
  double seconds;
  if (Tcl_GetDoubleFromObj(interp, objv[1], &seconds) != TCL_OK) {
    return TCL_ERROR;
  }
  if (seconds < 0) {
    Tcl_SetObjResult(interp, Tcl_NewStringObj("seconds must be >= 0", -1));
    return TCL_ERROR;
  }
  /* Default SIGALRM disposition (terminate) is the mechanism; make sure
   * no inherited ignore/handler defuses it. */
  signal(SIGALRM, SIG_DFL);
  alarm((unsigned int) (seconds + 0.999));
  return TCL_OK;
}

/* posix_exit ?code?: _exit, not exit — a forked child must never run the
 * host's atexit hooks (logger teardown, metrics dumps) that belong to the
 * process image it copied. */
static int
PosixExitCmd(void *cd, Tcl_Interp *interp, int objc, Tcl_Obj *const objv[])
{
  (void) cd;
  int code = 0;
  if (objc > 2) {
    Tcl_WrongNumArgs(interp, 1, objv, "?code?");
    return TCL_ERROR;
  }
  if (objc == 2 && Tcl_GetIntFromObj(interp, objv[1], &code) != TCL_OK) {
    return TCL_ERROR;
  }
  fflush(NULL);
  _exit(code);
}

int
Orfsfork_Init(Tcl_Interp *interp)
{
  if (Tcl_InitStubs(interp, "9.0", 0) == NULL) {
    return TCL_ERROR;
  }
  if (Tcl_Eval(interp, "namespace eval ::orfs {}") != TCL_OK) {
    return TCL_ERROR;
  }
  Tcl_CreateObjCommand(interp, "::orfs::posix_fork", PosixForkCmd, NULL,
                       NULL);
  Tcl_CreateObjCommand(interp, "::orfs::posix_waitpid", PosixWaitpidCmd,
                       NULL, NULL);
  Tcl_CreateObjCommand(interp, "::orfs::posix_exit", PosixExitCmd, NULL,
                       NULL);
  Tcl_CreateObjCommand(interp, "::orfs::posix_alarm", PosixAlarmCmd, NULL,
                       NULL);
  return Tcl_PkgProvide(interp, "orfsfork", "1.0");
}
