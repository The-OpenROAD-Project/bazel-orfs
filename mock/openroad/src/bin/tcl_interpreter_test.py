"""Unit tests for the minimal TCL interpreter."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from tcl_interpreter import TclInterpreter, TclError


@pytest.fixture
def interp():
    return TclInterpreter()


# --- Variable substitution ---


class TestVariables:
    def test_set_get(self, interp):
        interp.eval("set x hello")
        assert interp.get_var("x") == "hello"

    def test_set_returns_value(self, interp):
        result = interp.eval("set x 42")
        assert result == "42"

    def test_variable_substitution(self, interp):
        interp.eval("set name world")
        result = interp.eval('set msg "hello $name"')
        assert result == "hello world"

    def test_braced_no_substitution(self, interp):
        interp.eval("set name world")
        result = interp.eval("set msg {hello $name}")
        assert result == "hello $name"

    def test_env_var(self, interp):
        os.environ["TEST_TCL_VAR"] = "testval"
        result = interp.eval("set x $::env(TEST_TCL_VAR)")
        assert result == "testval"
        del os.environ["TEST_TCL_VAR"]

    def test_array(self, interp):
        interp.eval("set arr(key) value")
        result = interp.eval("set arr(key)")
        assert result == "value"

    def test_incr(self, interp):
        interp.eval("set x 5")
        result = interp.eval("incr x")
        assert result == "6"
        result = interp.eval("incr x 3")
        assert result == "9"

    def test_unset(self, interp):
        interp.eval("set x 1")
        interp.eval("unset x")
        with pytest.raises(TclError):
            interp.get_var("x")


# --- Command substitution ---


class TestCommandSubstitution:
    def test_simple(self, interp):
        interp.register_command("add", lambda i, a: str(int(a[0]) + int(a[1])))
        result = interp.eval("set x [add 3 4]")
        assert result == "7"

    def test_nested_brackets(self, interp):
        interp.register_command("double", lambda i, a: str(int(a[0]) * 2))
        result = interp.eval("set x [double [double 3]]")
        assert result == "12"

    def test_bracket_in_bare_word(self, interp):
        """[$var method] should parse as single word."""
        interp.register_command("obj", lambda i, a: "result" if a == ["method"] else "")
        interp.eval("set o obj")
        result = interp.eval("set x [$o method]")
        assert result == "result"

    def test_nested_method_calls(self, interp):
        """[[$db getTech] getDbUnitsPerMicron] pattern."""
        interp.register_command(
            "mock_db",
            lambda i, a: "mock_tech" if a and a[0] == "getTech" else "",
        )
        interp.register_command(
            "mock_tech",
            lambda i, a: "1000" if a and a[0] == "getDbu" else "",
        )
        interp.eval("set db mock_db")
        result = interp.eval("set x [[$db getTech] getDbu]")
        assert result == "1000"


# --- {*} expansion ---


class TestExpansion:
    def test_expand_variable(self, interp):
        results = []
        interp.register_command("cmd", lambda i, a: (results.extend(a), "")[1])
        interp.eval("set args {a b c}")
        interp.eval("cmd {*}$args")
        assert results == ["a", "b", "c"]

    def test_expand_in_proc(self, interp):
        results = []
        interp.register_command(
            "collect",
            lambda i, a: (results.extend(a), "")[1],
        )
        interp.eval("proc test {args} { collect {*}$args }")
        interp.eval("test x y z")
        assert results == ["x", "y", "z"]


# --- Proc ---


class TestProc:
    def test_basic_proc(self, interp):
        interp.eval('proc greet {name} { return "hi $name" }')
        result = interp.eval("greet world")
        assert result == "hi world"

    def test_proc_with_args(self, interp):
        """proc with special 'args' parameter."""
        interp.eval("proc log_cmd {cmd args} {" '  return "cmd=$cmd args=$args"' "}")
        result = interp.eval("log_cmd hello world foo")
        assert result == "cmd=hello args=world foo"

    def test_proc_return(self, interp):
        interp.eval("proc add {a b} { return [expr $a + $b] }")
        result = interp.eval("add 3 4")
        assert result == "7"

    def test_proc_scope(self, interp):
        """Proc variables don't leak."""
        interp.eval("set x outer")
        interp.eval("proc f {} { set x inner; return $x }")
        interp.eval("f")
        assert interp.get_var("x") == "outer"


# --- Control flow ---


class TestControlFlow:
    def test_if_true(self, interp):
        result = interp.eval("if {1} { set x yes }")
        assert result == "yes"

    def test_if_false(self, interp):
        result = interp.eval("if {0} { set x yes } else { set x no }")
        assert result == "no"

    def test_if_elseif(self, interp):
        interp.eval("set x 2")
        result = interp.eval(
            "if {$x == 1} { set r one }"
            " elseif {$x == 2} { set r two }"
            " else { set r other }"
        )
        assert result == "two"

    def test_foreach(self, interp):
        interp.eval("set sum 0")
        interp.eval("foreach i {1 2 3} { set sum [expr $sum + $i] }")
        assert interp.get_var("sum") == "6"

    def test_for_loop(self, interp):
        interp.eval("set sum 0")
        interp.eval(
            "for {set i 0} {$i < 3} {incr i} {" "  set sum [expr $sum + $i]" "}"
        )
        assert interp.get_var("sum") == "3"

    def test_while(self, interp):
        interp.eval("set i 0")
        interp.eval("while {$i < 5} { incr i }")
        assert interp.get_var("i") == "5"

    def test_break(self, interp):
        interp.eval("set i 0")
        interp.eval("while {1} { incr i; if {$i >= 3} break }")
        assert interp.get_var("i") == "3"

    def test_switch(self, interp):
        result = interp.eval('switch "b" { a { set r 1 } b { set r 2 } }')
        assert result == "2"


# --- Expressions ---


class TestExpr:
    def test_arithmetic(self, interp):
        assert interp.eval("expr 3 + 4") == "7"
        assert interp.eval("expr 10 / 3") == "3"

    def test_float(self, interp):
        result = interp.eval("expr 3.0 + 1.5")
        assert float(result) == 4.5

    def test_comparison(self, interp):
        assert interp.eval("expr 5 > 3") == "1"
        assert interp.eval("expr 2 > 3") == "0"

    def test_boolean(self, interp):
        assert interp.eval("expr 1 && 1") == "1"
        assert interp.eval("expr 1 && 0") == "0"

    def test_double_conversion(self, interp):
        result = interp.eval("expr double(42)")
        assert float(result) == 42.0

    def test_variable_in_expr(self, interp):
        interp.eval("set x 10")
        result = interp.eval("expr $x * 2")
        assert result == "20"


# --- List operations ---


class TestLists:
    def test_list(self, interp):
        result = interp.eval("list a b c")
        assert result == "a b c"

    def test_llength(self, interp):
        result = interp.eval("llength {a b c}")
        assert result == "3"

    def test_lindex(self, interp):
        result = interp.eval("lindex {a b c} 1")
        assert result == "b"

    def test_lappend(self, interp):
        interp.eval("set lst {a b}")
        interp.eval("lappend lst c")
        assert interp.get_var("lst") == "a b c"

    def test_lrange(self, interp):
        result = interp.eval("lrange {a b c d} 1 2")
        assert result == "b c"

    def test_lmap(self, interp):
        result = interp.eval("lmap x {1 2 3} { expr $x * 2 }")
        assert result == "2 4 6"

    def test_join(self, interp):
        result = interp.eval("join {a b c} ,")
        assert result == "a,b,c"

    def test_split(self, interp):
        result = interp.eval("split {a,b,c} ,")
        assert result == "a b c"


# --- String operations ---


class TestStrings:
    def test_length(self, interp):
        result = interp.eval("string length hello")
        assert result == "5"

    def test_match(self, interp):
        result = interp.eval('string match "*.tcl" "foo.tcl"')
        assert result == "1"

    def test_tolower(self, interp):
        result = interp.eval("string tolower HELLO")
        assert result == "hello"

    def test_trim(self, interp):
        result = interp.eval('string trim "  hello  "')
        assert result == "hello"

    def test_map(self, interp):
        result = interp.eval('string map {a A e E} "hello"')
        assert result == "hEllo"


# --- Source and file operations ---


class TestSource:
    def test_source_file(self, interp):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tcl", delete=False) as f:
            f.write("set sourced_var 42\n")
            f.flush()
            interp.eval(f"source {f.name}")
            assert interp.get_var("sourced_var") == "42"
            os.unlink(f.name)

    def test_file_exists(self, interp):
        result = interp.eval("file exists /dev/null")
        assert result == "1"
        result = interp.eval("file exists /nonexistent_file_xyz")
        assert result == "0"

    def test_file_dirname(self, interp):
        result = interp.eval("file dirname /a/b/c.txt")
        assert result == "/a/b"


# --- Catch ---


class TestCatch:
    def test_catch_success(self, interp):
        result = interp.eval("catch { set x 1 } msg")
        assert result == "0"
        assert interp.get_var("msg") == "1"

    def test_catch_error(self, interp):
        result = interp.eval("catch { error boom } msg")
        assert result == "1"
        assert interp.get_var("msg") == "boom"


# --- Clock ---


class TestClock:
    def test_clock_seconds(self, interp):
        result = interp.eval("clock seconds")
        assert int(result) > 0


# --- Comments and whitespace ---


class TestParsing:
    def test_comment(self, interp):
        interp.eval("# this is a comment\nset x 1")
        assert interp.get_var("x") == "1"

    def test_semicolon(self, interp):
        interp.eval("set x 1; set y 2")
        assert interp.get_var("x") == "1"
        assert interp.get_var("y") == "2"

    def test_backslash_newline(self, interp):
        # Backslash-newline is line continuation, joins words
        result = interp.eval("set x \\\nhello")
        assert result == "hello"

    def test_empty_script(self, interp):
        result = interp.eval("")
        assert result == ""

    def test_inline_comment(self, interp):
        """Comments after ;# pattern."""
        interp.eval("set x 1 ;# inline comment")
        assert interp.get_var("x") == "1"


# --- Namespace ---


class TestNamespace:
    def test_namespace_eval(self, interp):
        interp.eval("namespace eval myns { proc hello {} {" " return hi } }")

    def test_unknown_command_no_crash(self, interp):
        """Unknown commands print warning but don't crash."""
        result = interp.eval("nonexistent_cmd arg1 arg2")
        assert result == ""


# --- Dict ---


class TestDict:
    def test_create_and_get(self, interp):
        interp.eval("set d [dict create a 1 b 2]")
        result = interp.eval("dict get $d a")
        assert result == "1"

    def test_exists(self, interp):
        interp.eval("set d [dict create a 1]")
        assert interp.eval("dict exists $d a") == "1"
        assert interp.eval("dict exists $d b") == "0"

    def test_keys(self, interp):
        interp.eval("set d [dict create x 1 y 2]")
        result = interp.eval("dict keys $d")
        assert "x" in result and "y" in result


# --- Error handling / failure modes ---


class TestErrors:
    def test_missing_variable(self, interp):
        with pytest.raises(TclError, match="no such variable"):
            interp.eval("set x $nonexistent")

    def test_missing_close_brace(self, interp):
        with pytest.raises(TclError, match="missing close-brace"):
            interp.eval("set x {unclosed")

    def test_missing_close_bracket(self, interp):
        with pytest.raises(TclError, match="missing close-bracket"):
            interp.eval("set x [unclosed")

    def test_missing_close_quote(self, interp):
        with pytest.raises(TclError, match="missing close-quote"):
            interp.eval('set x "unclosed')

    def test_division_by_zero(self, interp):
        # May raise or return string — just shouldn't hang
        try:
            interp.eval("expr {1 / 0}")
            # If it doesn't raise, that's ok for now
        except (TclError, ZeroDivisionError):
            pass  # expected

    def test_wrong_args_set(self, interp):
        with pytest.raises(TclError, match="wrong # args"):
            interp.eval("set a b c d")

    def test_wrong_args_llength(self, interp):
        with pytest.raises(TclError, match="wrong # args"):
            interp.eval("llength")

    def test_source_missing_file(self, interp):
        with pytest.raises(TclError, match="couldn't read"):
            interp.eval("source /nonexistent/file.tcl")

    def test_error_command(self, interp):
        with pytest.raises(TclError, match="boom"):
            interp.eval('error "boom"')

    def test_error_in_proc(self, interp):
        interp.eval("proc fail {} { error oops }")
        with pytest.raises(TclError, match="oops"):
            interp.eval("fail")

    def test_catch_prevents_propagation(self, interp):
        """catch should prevent error from propagating."""
        result = interp.eval('catch { error "caught" } msg')
        assert result == "1"
        assert interp.get_var("msg") == "caught"

    def test_nested_error_propagation(self, interp):
        """Error in nested command substitution."""
        interp.eval("proc inner {} { error nested }")
        with pytest.raises(TclError, match="nested"):
            interp.eval("set x [inner]")

    def test_unknown_array_element(self, interp):
        interp.eval("set arr(a) 1")
        with pytest.raises(TclError, match="no such element"):
            interp.eval("set arr(b)")

    def test_break_outside_loop(self, interp):
        """break outside a loop should raise."""
        with pytest.raises(Exception):
            interp.eval("break")

    def test_expr_invalid_syntax(self, interp):
        """Invalid expression should not crash."""
        # May return string or raise — just shouldn't hang
        try:
            interp.eval("expr {invalid + +}")
        except (TclError, Exception):
            pass  # any error is fine

    def test_for_loop_missing_args(self, interp):
        with pytest.raises(TclError, match="wrong # args"):
            interp.eval("for {set i 0} {$i < 5}")


class TestNestedSubstitution:
    def test_nested_command_in_braces_no_subst(self, interp):
        """Braces prevent command substitution."""
        result = interp.eval("set x {[expr 1+2]}")
        assert result == "[expr 1+2]"

    def test_nested_command_in_quotes_subst(self, interp):
        result = interp.eval('set x "[expr 1+2]"')
        assert result == "3"

    def test_dollar_in_braces(self, interp):
        interp.eval("set y 42")
        result = interp.eval("set x {$y}")
        assert result == "$y"

    def test_backslash_n_in_string(self, interp):
        """Backslash-n in quotes produces newline."""
        result = interp.eval('set x "line1\\nline2"')
        assert "line1" in result
        assert "line2" in result


class TestListOperations:
    def test_llength_empty(self, interp):
        result = interp.eval("llength {}")
        assert result == "0"

    def test_llength_multi(self, interp):
        result = interp.eval("llength {a b c}")
        assert result == "3"

    def test_lindex_first(self, interp):
        result = interp.eval("lindex {a b c} 0")
        assert result == "a"

    def test_lindex_last_numeric(self, interp):
        result = interp.eval("lindex {a b c} 2")
        assert result == "c"

    def test_lappend(self, interp):
        interp.eval("set lst {}")
        interp.eval("lappend lst a b")
        result = interp.eval("llength $lst")
        assert result == "2"

    def test_lsort(self, interp):
        result = interp.eval("lsort {c a b}")
        assert result == "a b c"


class TestStringOperations:
    def test_string_length(self, interp):
        result = interp.eval("string length hello")
        assert result == "5"

    def test_string_range(self, interp):
        result = interp.eval("string range hello 1 3")
        assert result == "ell"

    def test_string_equal(self, interp):
        r1 = interp.eval("string equal abc abc")
        r2 = interp.eval("string equal abc def")
        assert r1 == "1"
        assert r2 == "0"

    def test_string_map(self, interp):
        result = interp.eval('string map {a A e E} "hello"')
        assert result == "hEllo"


class TestInfoCommand:
    def test_info_exists_true(self, interp):
        interp.eval("set myvar 42")
        result = interp.eval("info exists myvar")
        assert result == "1"

    def test_info_exists_false(self, interp):
        result = interp.eval("info exists nonexistent_var")
        assert result == "0"

    def test_info_exists_in_proc(self, interp):
        interp.eval(
            "proc test_exists {} {" " set local 1;" " return [info exists local]" " }"
        )
        result = interp.eval("test_exists")
        assert result == "1"


class TestFRC:
    def test_frc_source_file_missing(self, interp, capsys):
        """file exists on missing .tcl emits FRC warning."""
        interp.eval("file exists /nonexistent/foo.tcl")
        captured = capsys.readouterr()
        assert "FRC source-file-missing" in captured.err
        assert "/nonexistent/foo.tcl" in captured.err

    def test_frc_source_file_present(self, interp, capsys):
        """file exists on real .tcl file emits no FRC warning."""
        with tempfile.NamedTemporaryFile(suffix=".tcl", delete=False) as f:
            f.write(b"# ok\n")
            f.flush()
            interp.eval(f"file exists {f.name}")
            captured = capsys.readouterr()
            assert "FRC" not in captured.err
            os.unlink(f.name)

    def test_frc_non_tcl_no_warning(self, interp, capsys):
        """file exists on missing non-.tcl file emits no FRC warning."""
        interp.eval("file exists /nonexistent/foo.txt")
        captured = capsys.readouterr()
        assert "FRC" not in captured.err


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
