"""Minimal TCL interpreter for executing ORFS stage scripts.

Implements the subset of TCL needed by OpenROAD-flow-scripts:
source, set, if/else/elseif, expr, proc, foreach, list ops,
string ops, file ops, env array access, catch, puts.

Commands are registered via register_command() so lint OpenROAD/Yosys
commands can be plugged in.
"""

import math
import os
import re
import shlex
import sys


class TclError(Exception):
    """Error raised during TCL interpretation."""

    def __init__(self, message, script=None, line=None):
        self.script = script
        self.line = line
        prefix = ""
        if script and line is not None:
            prefix = f"{script}:{line}: "
        super().__init__(f"{prefix}{message}")


class TclReturn(Exception):
    """Control flow: return from proc."""

    def __init__(self, value=""):
        self.value = value


class TclBreak(Exception):
    """Control flow: break from loop."""


class TclContinue(Exception):
    """Control flow: continue in loop."""


class TclInterpreter:
    """Minimal TCL interpreter for ORFS scripts."""

    def __init__(self):
        self.variables = {}
        self.arrays = {}
        self.commands = {}
        self.procs = {}
        self._source_stack = []  # track nested source calls
        self._register_builtins()

    # --- Public API ---

    def register_command(self, name, func):
        """Register a command handler: func(interp, args) -> str."""
        self.commands[name] = func

    def set_var(self, name, value):
        """Set a variable."""
        self.variables[name] = str(value)

    def get_var(self, name):
        """Get a variable value."""
        if name in self.variables:
            return self.variables[name]
        raise TclError(f"can't read \"{name}\": no such variable")

    def set_array(self, array_name, key, value):
        """Set an array element."""
        if array_name not in self.arrays:
            self.arrays[array_name] = {}
        self.arrays[array_name][key] = str(value)

    def get_array(self, array_name, key):
        """Get an array element."""
        if array_name in self.arrays and key in self.arrays[array_name]:
            return self.arrays[array_name][key]
        raise TclError(
            f"can't read \"{array_name}({key})\": no such element in array"
        )

    def eval(self, script, source_file=None):
        """Evaluate a TCL script string. Returns the result of the last command."""
        if source_file:
            self._source_stack.append(source_file)
        try:
            return self._eval_script(script)
        finally:
            if source_file:
                self._source_stack.pop()

    def eval_file(self, path):
        """Evaluate a TCL file."""
        try:
            with open(path) as f:
                script = f.read()
        except OSError as e:
            raise TclError(f"couldn't read file \"{path}\": {e}")
        return self.eval(script, source_file=path)

    # --- Script parsing ---

    def _eval_script(self, script):
        """Parse and evaluate a script (sequence of commands)."""
        result = ""
        commands = self._parse_commands(script)
        for word_infos in commands:
            if not word_infos:
                continue
            # Substitute variables and nested commands, handle {*} expansion
            # word_infos is list of (word, is_braced) tuples
            expanded = []
            for w, is_braced in word_infos:
                if w.startswith("{*}") and not is_braced:
                    # {*} prefix: substitute the rest and expand as list
                    rest = self._substitute(w[3:])
                    expanded.extend(self._parse_list(rest))
                elif is_braced:
                    # Braced words: no substitution
                    expanded.append(w)
                else:
                    expanded.append(self._substitute(w))
            result = self._invoke(expanded)
        return result

    def _parse_commands(self, script):
        """Parse a script into a list of command word-lists.

        Returns list of lists of (word, is_braced) tuples.
        Handles: semicolons, newlines, braces, quotes, backslash continuation,
        comments.
        """
        commands = []
        current_words = []
        i = 0
        n = len(script)

        while i < n:
            c = script[i]

            # Skip whitespace (not newlines)
            if c in " \t":
                i += 1
                continue

            # Backslash-newline continuation
            if c == "\\" and i + 1 < n and script[i + 1] == "\n":
                i += 2
                # Skip leading whitespace on next line
                while i < n and script[i] in " \t":
                    i += 1
                continue

            # Command separators
            if c in "\n;":
                if current_words:
                    commands.append(current_words)
                    current_words = []
                i += 1
                continue

            # Comments (only at start of command)
            if c == "#" and not current_words:
                while i < n and script[i] != "\n":
                    if script[i] == "\\" and i + 1 < n and script[i + 1] == "\n":
                        i += 2  # backslash-newline in comment
                        continue
                    i += 1
                continue

            # Check for {*} expansion prefix
            if c == "{" and i + 2 < n and script[i + 1] == "*" and script[i + 2] == "}":
                # {*} expansion — parse the next word and prepend {*}
                i += 3
                if i < n and script[i] not in " \t\n;":
                    word, i = self._parse_word(script, i)
                    current_words.append(("{*}" + word, False))
                continue

            # Parse a word, tracking if it's braced
            is_braced = (c == "{")
            word, i = self._parse_word(script, i)
            current_words.append((word, is_braced))

        if current_words:
            commands.append(current_words)
        return commands

    def _parse_word(self, script, i):
        """Parse a single word starting at position i. Returns (word, new_i)."""
        n = len(script)
        c = script[i]

        if c == "{":
            return self._parse_braced(script, i)
        elif c == '"':
            return self._parse_quoted(script, i)
        else:
            return self._parse_bare(script, i)

    def _parse_braced(self, script, i):
        """Parse a brace-delimited word {....}. No substitutions."""
        depth = 1
        i += 1  # skip opening {
        start = i
        n = len(script)
        while i < n:
            c = script[i]
            if c == "\\" and i + 1 < n:
                i += 2  # skip escaped char
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return script[start:i], i + 1
            i += 1
        raise TclError("missing close-brace")

    def _parse_quoted(self, script, i):
        """Parse a double-quoted word "...". Allows substitutions."""
        i += 1  # skip opening "
        parts = []
        n = len(script)
        start = i
        while i < n:
            c = script[i]
            if c == "\\":
                parts.append(script[start:i])
                if i + 1 < n:
                    escaped, i = self._parse_backslash(script, i)
                    parts.append(escaped)
                    start = i
                    continue
                else:
                    i += 1
                    start = i
            elif c == '"':
                parts.append(script[start:i])
                return "".join(parts), i + 1
            else:
                i += 1
        raise TclError("missing close-quote")

    def _parse_bare(self, script, i):
        """Parse a bare (unquoted) word.

        Brackets [...] are part of the word (command substitution).
        """
        parts = []
        n = len(script)
        start = i
        bracket_depth = 0
        while i < n:
            c = script[i]
            if c == "[":
                bracket_depth += 1
                i += 1
            elif c == "]":
                if bracket_depth > 0:
                    bracket_depth -= 1
                    i += 1
                else:
                    break
            elif c in " \t\n;" and bracket_depth == 0:
                break
            elif c == "\\" and bracket_depth == 0:
                parts.append(script[start:i])
                if i + 1 < n:
                    if script[i + 1] == "\n":
                        break
                    escaped, i = self._parse_backslash(script, i)
                    parts.append(escaped)
                    start = i
                    continue
                else:
                    i += 1
                    start = i
            else:
                i += 1
        parts.append(script[start:i])
        return "".join(parts), i

    def _parse_backslash(self, script, i):
        """Parse a backslash escape at position i. Returns (char, new_i)."""
        # i points at the backslash
        next_c = script[i + 1] if i + 1 < len(script) else ""
        escape_map = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"',
                      "{": "{", "}": "}", "[": "[", "]": "]", "$": "$"}
        if next_c in escape_map:
            return escape_map[next_c], i + 2
        return next_c, i + 2

    # --- Substitution ---

    def _substitute(self, word):
        """Perform variable and command substitution on a word."""
        result = []
        i = 0
        n = len(word)

        while i < n:
            c = word[i]

            if c == "$":
                val, i = self._subst_variable(word, i)
                result.append(val)
            elif c == "[":
                val, i = self._subst_command(word, i)
                result.append(val)
            elif c == "\\":
                if i + 1 < n:
                    escaped, i = self._parse_backslash(word, i)
                    result.append(escaped)
                else:
                    result.append("\\")
                    i += 1
            else:
                result.append(c)
                i += 1

        return "".join(result)

    def _subst_variable(self, word, i):
        """Substitute a variable starting with $ at position i."""
        i += 1  # skip $
        n = len(word)

        if i >= n:
            return "$", i

        # ${varname} form
        if word[i] == "{":
            end = word.index("}", i + 1) if "}" in word[i + 1:] else -1
            if end == -1:
                raise TclError("missing close-brace for variable name")
            end = word.index("}", i + 1)
            varname = word[i + 1:end]
            return self.get_var(varname), end + 1

        # $::env(NAME) or $::namespace::var
        if word[i:i + 2] == "::":
            return self._subst_namespaced_var(word, i)

        # Regular variable name
        start = i
        while i < n and (word[i].isalnum() or word[i] == "_"):
            i += 1

        varname = word[start:i]
        if not varname:
            return "$", i

        # Array element: $name(key)
        if i < n and word[i] == "(":
            key_start = i + 1
            depth = 1
            i += 1
            while i < n and depth > 0:
                if word[i] == "(":
                    depth += 1
                elif word[i] == ")":
                    depth -= 1
                i += 1
            key = self._substitute(word[key_start:i - 1])
            return self.get_array(varname, key), i

        return self.get_var(varname), i

    def _subst_namespaced_var(self, word, i):
        """Handle $::env(NAME) and $::namespace::var patterns."""
        # Collect the full namespaced name
        start = i
        n = len(word)

        while i < n and (word[i].isalnum() or word[i] == "_" or word[i] == ":"):
            i += 1

        name = word[start:i]  # e.g., "::env"

        # Array access: $::env(KEY)
        if i < n and word[i] == "(":
            key_start = i + 1
            depth = 1
            i += 1
            while i < n and depth > 0:
                if word[i] == "(":
                    depth += 1
                elif word[i] == ")":
                    depth -= 1
                i += 1
            key = self._substitute(word[key_start:i - 1])

            if name == "::env":
                val = os.environ.get(key, "")
                return val, i
            return self.get_array(name.lstrip(":"), key), i

        # Plain namespaced variable
        return self.get_var(name.lstrip(":")), i

    def _subst_command(self, word, i):
        """Substitute a [command] at position i."""
        depth = 1
        i += 1  # skip [
        start = i
        n = len(word)
        while i < n:
            if word[i] == "[":
                depth += 1
            elif word[i] == "]":
                depth -= 1
                if depth == 0:
                    cmd_script = word[start:i]
                    result = self._eval_script(cmd_script)
                    return result, i + 1
            elif word[i] == "\\":
                i += 1  # skip next char
            i += 1
        raise TclError("missing close-bracket")

    # --- Command invocation ---

    def invoke(self, words):
        """Invoke a command given a list of already-expanded words."""
        return self._invoke(words)

    def _invoke(self, words):
        """Invoke a command given expanded words."""
        if not words:
            return ""
        cmd_name = words[0]
        args = words[1:]

        # Check registered commands first
        if cmd_name in self.commands:
            return self.commands[cmd_name](self, args) or ""

        # Then procs
        if cmd_name in self.procs:
            return self._call_proc(cmd_name, args)

        # Namespace-qualified commands (e.g., ord::get_db)
        # Try stripping namespace
        if "::" in cmd_name:
            short = cmd_name.split("::")[-1]
            if short in self.commands:
                return self.commands[short](self, args) or ""

        # Unknown command — silently ignore (ORFS scripts reference many
        # OpenROAD internals we don't need to implement)
        return ""

    def _call_proc(self, name, args):
        """Call a user-defined proc."""
        params, body = self.procs[name]

        # Save current variables (simple scope)
        saved = dict(self.variables)
        try:
            # Handle 'args' parameter (variadic)
            if params and params[-1] == "args":
                for i, p in enumerate(params[:-1]):
                    if i < len(args):
                        self.variables[p] = args[i]
                    else:
                        raise TclError(
                            f"wrong # args: should be \"{name} {' '.join(params)}\""
                        )
                self.variables["args"] = " ".join(args[len(params) - 1:])
            else:
                # Handle default values
                required = []
                defaults = []
                for p in params:
                    if isinstance(p, list) and len(p) == 2:
                        defaults.append(p)
                    else:
                        required.append(p)
                        defaults.append(None)

                for i, p in enumerate(params):
                    pname = p[0] if isinstance(p, list) else p
                    if i < len(args):
                        self.variables[pname] = args[i]
                    elif isinstance(p, list) and len(p) == 2:
                        self.variables[pname] = p[1]
                    else:
                        raise TclError(
                            f"wrong # args: should be \"{name} {' '.join(str(p) for p in params)}\""
                        )

            result = self._eval_script(body)
            return result
        except TclReturn as ret:
            return ret.value
        finally:
            self.variables = saved

    # --- Builtin commands ---

    def _register_builtins(self):
        """Register TCL builtin commands."""
        self.commands["set"] = self._cmd_set
        self.commands["unset"] = self._cmd_unset
        self.commands["puts"] = self._cmd_puts
        self.commands["proc"] = self._cmd_proc
        self.commands["if"] = self._cmd_if
        self.commands["for"] = self._cmd_for
        self.commands["foreach"] = self._cmd_foreach
        self.commands["while"] = self._cmd_while
        self.commands["expr"] = self._cmd_expr
        self.commands["return"] = self._cmd_return
        self.commands["break"] = self._cmd_break
        self.commands["continue"] = self._cmd_continue
        self.commands["source"] = self._cmd_source
        self.commands["catch"] = self._cmd_catch
        self.commands["error"] = self._cmd_error
        self.commands["list"] = self._cmd_list
        self.commands["lappend"] = self._cmd_lappend
        self.commands["lindex"] = self._cmd_lindex
        self.commands["llength"] = self._cmd_llength
        self.commands["lrange"] = self._cmd_lrange
        self.commands["lsort"] = self._cmd_lsort
        self.commands["lsearch"] = self._cmd_lsearch
        self.commands["lreplace"] = self._cmd_lreplace
        self.commands["lmap"] = self._cmd_lmap
        self.commands["concat"] = self._cmd_concat
        self.commands["join"] = self._cmd_join
        self.commands["split"] = self._cmd_split
        self.commands["string"] = self._cmd_string
        self.commands["regexp"] = self._cmd_regexp
        self.commands["regsub"] = self._cmd_regsub
        self.commands["file"] = self._cmd_file
        self.commands["glob"] = self._cmd_glob
        self.commands["open"] = self._cmd_open
        self.commands["close"] = self._cmd_close
        self.commands["read"] = self._cmd_read
        self.commands["gets"] = self._cmd_gets
        self.commands["info"] = self._cmd_info
        self.commands["array"] = self._cmd_array
        self.commands["global"] = self._cmd_global
        self.commands["upvar"] = self._cmd_upvar
        self.commands["uplevel"] = self._cmd_uplevel
        self.commands["incr"] = self._cmd_incr
        self.commands["append"] = self._cmd_append
        self.commands["format"] = self._cmd_format
        self.commands["scan"] = self._cmd_scan
        self.commands["switch"] = self._cmd_switch
        self.commands["rename"] = self._cmd_rename
        self.commands["eval"] = self._cmd_eval
        self.commands["namespace"] = self._cmd_namespace
        self.commands["package"] = self._cmd_package
        self.commands["variable"] = self._cmd_variable
        self.commands["dict"] = self._cmd_dict
        self.commands["apply"] = self._cmd_apply
        self.commands["after"] = self._cmd_after
        self.commands["clock"] = self._cmd_clock
        self.commands["tee"] = self._cmd_tee

    def _cmd_set(self, interp, args):
        if len(args) == 1:
            # Handle array get: set name(key)
            m = re.match(r"^(\w+)\((.+)\)$", args[0])
            if m:
                return self.get_array(m.group(1), m.group(2))
            return self.get_var(args[0])
        if len(args) == 2:
            # Handle array set: set name(key) value
            m = re.match(r"^(\w+)\((.+)\)$", args[0])
            if m:
                self.set_array(m.group(1), m.group(2), args[1])
                return args[1]
            self.variables[args[0]] = args[1]
            return args[1]
        raise TclError(
            "wrong # args: should be \"set varName ?newValue?\""
        )

    def _cmd_unset(self, interp, args):
        for name in args:
            if name.startswith("-"):
                continue
            self.variables.pop(name, None)
        return ""

    def _cmd_puts(self, interp, args):
        # puts ?-nonewline? ?channelId? string
        nonewline = False
        channel = "stdout"
        msg = ""
        remaining = list(args)
        if remaining and remaining[0] == "-nonewline":
            nonewline = True
            remaining.pop(0)
        if len(remaining) == 2:
            channel = remaining[0]
            msg = remaining[1]
        elif len(remaining) == 1:
            msg = remaining[0]
        end = "" if nonewline else "\n"
        out = sys.stderr if channel == "stderr" else sys.stdout
        out.write(msg + end)
        return ""

    def _cmd_proc(self, interp, args):
        if len(args) != 3:
            raise TclError("wrong # args: should be \"proc name args body\"")
        name, params_str, body = args
        params = self._parse_list(params_str)
        self.procs[name] = (params, body)
        return ""

    def _cmd_if(self, interp, args):
        """if expr1 ?then? body1 ?elseif expr2 body2? ... ?else bodyN?"""
        i = 0
        while i < len(args):
            # Evaluate condition
            cond = args[i]
            i += 1

            # Skip optional 'then'
            if i < len(args) and args[i] == "then":
                i += 1

            if i >= len(args):
                raise TclError("wrong # args: no body for if/elseif")

            body = args[i]
            i += 1

            if self._expr_bool(cond):
                return self._eval_script(body)

            # Check for elseif or else
            if i < len(args):
                if args[i] == "elseif":
                    i += 1
                    continue
                elif args[i] == "else":
                    i += 1
                    if i < len(args):
                        return self._eval_script(args[i])
                    raise TclError("wrong # args: no body for else")
            break
        return ""

    def _cmd_for(self, interp, args):
        if len(args) != 4:
            raise TclError("wrong # args: should be \"for start test next body\"")
        init, test, step, body = args
        self._eval_script(init)
        result = ""
        while self._expr_bool(test):
            try:
                result = self._eval_script(body)
            except TclBreak:
                break
            except TclContinue:
                pass
            self._eval_script(step)
        return result

    def _cmd_foreach(self, interp, args):
        if len(args) < 3:
            raise TclError("wrong # args: should be \"foreach varList list body\"")
        varname = args[0]
        items = self._parse_list(args[1])
        body = args[2]
        result = ""
        for item in items:
            self.variables[varname] = item
            try:
                result = self._eval_script(body)
            except TclBreak:
                break
            except TclContinue:
                continue
        return result

    def _cmd_while(self, interp, args):
        if len(args) != 2:
            raise TclError("wrong # args: should be \"while test body\"")
        test, body = args
        result = ""
        while self._expr_bool(test):
            try:
                result = self._eval_script(body)
            except TclBreak:
                break
            except TclContinue:
                continue
        return result

    def _cmd_expr(self, interp, args):
        expr_str = " ".join(args)
        return str(self._eval_expr(expr_str))

    def _cmd_return(self, interp, args):
        value = args[0] if args else ""
        # Handle -code option
        if len(args) >= 2 and args[0] == "-code":
            code = args[1]
            value = args[2] if len(args) > 2 else ""
            if code == "error":
                raise TclError(value)
        raise TclReturn(value)

    def _cmd_break(self, interp, args):
        raise TclBreak()

    def _cmd_continue(self, interp, args):
        raise TclContinue()

    def _cmd_source(self, interp, args):
        if len(args) != 1:
            raise TclError("wrong # args: should be \"source fileName\"")
        path = args[0]
        # Resolve relative paths against current source file directory
        if not os.path.isabs(path) and self._source_stack:
            base_dir = os.path.dirname(self._source_stack[-1])
            candidate = os.path.join(base_dir, path)
            if os.path.isfile(candidate):
                path = candidate
        return self.eval_file(path)

    def _cmd_catch(self, interp, args):
        if len(args) < 1:
            raise TclError("wrong # args: should be \"catch script ?resultVar?\"")
        script = args[0]
        result_var = args[1] if len(args) > 1 else None
        try:
            result = self._eval_script(script)
            if result_var:
                self.variables[result_var] = result
            return "0"
        except TclError as e:
            if result_var:
                self.variables[result_var] = str(e)
            return "1"
        except TclReturn as e:
            if result_var:
                self.variables[result_var] = e.value
            return "2"
        except Exception as e:
            if result_var:
                self.variables[result_var] = str(e)
            return "1"

    def _cmd_error(self, interp, args):
        if len(args) < 1:
            raise TclError("wrong # args: should be \"error message\"")
        raise TclError(args[0])

    # --- List commands ---

    def _parse_list(self, s):
        """Parse a TCL list string into Python list of strings."""
        if not s or not s.strip():
            return []
        result = []
        i = 0
        n = len(s)
        while i < n:
            while i < n and s[i] in " \t\n":
                i += 1
            if i >= n:
                break
            if s[i] == "{":
                word, i = self._parse_braced(s, i)
                result.append(word)
            elif s[i] == '"':
                word, i = self._parse_quoted(s, i)
                result.append(word)
            else:
                start = i
                while i < n and s[i] not in " \t\n":
                    if s[i] == "\\" and i + 1 < n:
                        i += 2
                    else:
                        i += 1
                result.append(s[start:i])
        return result

    def _to_list(self, items):
        """Convert Python list to TCL list string."""
        parts = []
        for item in items:
            s = str(item)
            if not s or " " in s or "\t" in s or "\n" in s or "{" in s or "}" in s or '"' in s:
                parts.append("{" + s + "}")
            else:
                parts.append(s)
        return " ".join(parts)

    def _cmd_list(self, interp, args):
        return self._to_list(args)

    def _cmd_lappend(self, interp, args):
        if len(args) < 1:
            raise TclError("wrong # args: should be \"lappend varName ?value ...?\"")
        varname = args[0]
        current = self.variables.get(varname, "")
        items = self._parse_list(current) if current else []
        items.extend(args[1:])
        result = self._to_list(items)
        self.variables[varname] = result
        return result

    def _cmd_lindex(self, interp, args):
        if len(args) < 2:
            raise TclError("wrong # args: should be \"lindex list index\"")
        items = self._parse_list(args[0])
        try:
            idx = int(args[1])
            if idx == -1 or idx == "end":
                idx = len(items) - 1
            if 0 <= idx < len(items):
                return items[idx]
        except (ValueError, IndexError):
            pass
        return ""

    def _cmd_llength(self, interp, args):
        if len(args) != 1:
            raise TclError("wrong # args: should be \"llength list\"")
        return str(len(self._parse_list(args[0])))

    def _cmd_lrange(self, interp, args):
        if len(args) != 3:
            raise TclError("wrong # args: should be \"lrange list first last\"")
        items = self._parse_list(args[0])
        first = self._list_index(args[1], len(items))
        last = self._list_index(args[2], len(items))
        return self._to_list(items[first:last + 1])

    def _cmd_lsort(self, interp, args):
        items = self._parse_list(args[-1])
        reverse = "-decreasing" in args
        unique = "-unique" in args
        if unique:
            items = list(dict.fromkeys(items))
        items.sort(reverse=reverse)
        return self._to_list(items)

    def _cmd_lsearch(self, interp, args):
        # Simple: lsearch list pattern
        if len(args) < 2:
            return "-1"
        items = self._parse_list(args[-2])
        pattern = args[-1]
        for idx, item in enumerate(items):
            if item == pattern:
                return str(idx)
        return "-1"

    def _cmd_lreplace(self, interp, args):
        if len(args) < 3:
            raise TclError("wrong # args")
        items = self._parse_list(args[0])
        first = self._list_index(args[1], len(items))
        last = self._list_index(args[2], len(items))
        new_items = args[3:]
        items[first:last + 1] = new_items
        return self._to_list(items)

    def _list_index(self, idx_str, length):
        """Convert TCL list index to Python int."""
        if idx_str == "end":
            return length - 1
        if idx_str.startswith("end-"):
            return length - 1 - int(idx_str[4:])
        return max(0, int(idx_str))

    def _cmd_lmap(self, interp, args):
        """lmap varName list body — like foreach but collects results."""
        if len(args) < 3:
            raise TclError("wrong # args: should be \"lmap varList list body\"")
        varname = args[0]
        items = self._parse_list(args[1])
        body = args[2]
        results = []
        for item in items:
            self.variables[varname] = item
            try:
                r = self._eval_script(body)
                results.append(r)
            except TclBreak:
                break
            except TclContinue:
                continue
        return self._to_list(results)

    def _cmd_concat(self, interp, args):
        all_items = []
        for a in args:
            all_items.extend(self._parse_list(a))
        return self._to_list(all_items)

    def _cmd_join(self, interp, args):
        items = self._parse_list(args[0])
        sep = args[1] if len(args) > 1 else " "
        return sep.join(items)

    def _cmd_split(self, interp, args):
        s = args[0] if args else ""
        chars = args[1] if len(args) > 1 else " "
        if len(chars) == 1:
            return self._to_list(s.split(chars))
        # Split on any of the chars
        result = []
        current = []
        for c in s:
            if c in chars:
                result.append("".join(current))
                current = []
            else:
                current.append(c)
        result.append("".join(current))
        return self._to_list(result)

    # --- String commands ---

    def _cmd_string(self, interp, args):
        if not args:
            raise TclError("wrong # args")
        subcmd = args[0]
        sargs = args[1:]

        if subcmd == "length":
            return str(len(sargs[0])) if sargs else "0"
        elif subcmd == "index":
            s = sargs[0] if sargs else ""
            idx = int(sargs[1]) if len(sargs) > 1 else 0
            return s[idx] if 0 <= idx < len(s) else ""
        elif subcmd == "range":
            s = sargs[0]
            first = self._list_index(sargs[1], len(s))
            last = self._list_index(sargs[2], len(s))
            return s[first:last + 1]
        elif subcmd == "equal":
            return "1" if sargs[0] == sargs[1] else "0"
        elif subcmd == "compare":
            a, b = sargs[0], sargs[1]
            return str((a > b) - (a < b))
        elif subcmd == "match":
            # Glob-style matching
            import fnmatch
            return "1" if fnmatch.fnmatch(sargs[1], sargs[0]) else "0"
        elif subcmd == "map":
            mapping = self._parse_list(sargs[0])
            s = sargs[1]
            for i in range(0, len(mapping) - 1, 2):
                s = s.replace(mapping[i], mapping[i + 1])
            return s
        elif subcmd == "tolower":
            return sargs[0].lower() if sargs else ""
        elif subcmd == "toupper":
            return sargs[0].upper() if sargs else ""
        elif subcmd == "trim":
            s = sargs[0]
            chars = sargs[1] if len(sargs) > 1 else None
            return s.strip(chars)
        elif subcmd == "trimleft":
            s = sargs[0]
            chars = sargs[1] if len(sargs) > 1 else None
            return s.lstrip(chars)
        elif subcmd == "trimright":
            s = sargs[0]
            chars = sargs[1] if len(sargs) > 1 else None
            return s.rstrip(chars)
        elif subcmd == "first":
            return str(sargs[1].find(sargs[0]))
        elif subcmd == "last":
            return str(sargs[1].rfind(sargs[0]))
        elif subcmd == "replace":
            s = sargs[0]
            first = int(sargs[1])
            last = int(sargs[2])
            replacement = sargs[3] if len(sargs) > 3 else ""
            return s[:first] + replacement + s[last + 1:]
        elif subcmd == "repeat":
            return sargs[0] * int(sargs[1])
        elif subcmd == "is":
            # string is integer/double/boolean/alpha/...
            type_name = sargs[0]
            # Skip -strict flag
            val_args = [a for a in sargs[1:] if not a.startswith("-")]
            val = val_args[0] if val_args else ""
            if type_name == "integer":
                try:
                    int(val)
                    return "1"
                except ValueError:
                    return "0"
            elif type_name == "double":
                try:
                    float(val)
                    return "1"
                except ValueError:
                    return "0"
            elif type_name == "boolean":
                return "1" if val.lower() in ("0", "1", "true", "false", "yes", "no", "on", "off") else "0"
            return "0"
        elif subcmd == "cat":
            return "".join(sargs)
        else:
            raise TclError(f"unknown string subcommand \"{subcmd}\"")

    def _cmd_regexp(self, interp, args):
        # regexp ?switches? exp string ?matchVar? ?subMatchVar ...?
        switches = []
        remaining = list(args)
        while remaining and remaining[0].startswith("-"):
            if remaining[0] == "--":
                remaining.pop(0)
                break
            switches.append(remaining.pop(0))
        if len(remaining) < 2:
            raise TclError("wrong # args")
        pattern = remaining[0]
        string = remaining[1]
        match_vars = remaining[2:]
        flags = 0
        if "-nocase" in switches:
            flags |= re.IGNORECASE
        m = re.search(pattern, string, flags)
        if m and match_vars:
            for i, var in enumerate(match_vars):
                if i == 0:
                    self.variables[var] = m.group(0)
                elif i <= len(m.groups()):
                    self.variables[var] = m.group(i) or ""
                else:
                    self.variables[var] = ""
        return "1" if m else "0"

    def _cmd_regsub(self, interp, args):
        remaining = list(args)
        all_flag = False
        while remaining and remaining[0].startswith("-"):
            if remaining[0] == "-all":
                all_flag = True
            elif remaining[0] == "--":
                remaining.pop(0)
                break
            remaining.pop(0)
        if len(remaining) < 3:
            raise TclError("wrong # args")
        pattern, string, replacement = remaining[0], remaining[1], remaining[2]
        result_var = remaining[3] if len(remaining) > 3 else None
        # TCL uses \1 for backrefs, Python uses \1 too
        count = 0 if all_flag else 1
        result = re.sub(pattern, replacement, string, count=count)
        if result_var:
            self.variables[result_var] = result
            return str(len(re.findall(pattern, string)))
        return result

    # --- File commands ---

    def _cmd_file(self, interp, args):
        if not args:
            raise TclError("wrong # args")
        subcmd = args[0]
        sargs = args[1:]
        if subcmd == "exists":
            return "1" if os.path.exists(sargs[0]) else "0"
        elif subcmd == "dirname":
            return os.path.dirname(sargs[0])
        elif subcmd == "tail":
            return os.path.basename(sargs[0])
        elif subcmd == "join":
            return os.path.join(*sargs)
        elif subcmd == "extension":
            return os.path.splitext(sargs[0])[1]
        elif subcmd == "rootname":
            return os.path.splitext(sargs[0])[0]
        elif subcmd == "normalize":
            return os.path.normpath(sargs[0])
        elif subcmd == "isfile":
            return "1" if os.path.isfile(sargs[0]) else "0"
        elif subcmd == "isdirectory":
            return "1" if os.path.isdir(sargs[0]) else "0"
        elif subcmd == "mkdir":
            for d in sargs:
                os.makedirs(d, exist_ok=True)
            return ""
        elif subcmd == "delete":
            force = "-force" in sargs
            for f in sargs:
                if f == "-force":
                    continue
                try:
                    if os.path.isdir(f):
                        import shutil
                        shutil.rmtree(f)
                    elif os.path.exists(f):
                        os.remove(f)
                    elif not force:
                        raise TclError(f"could not delete \"{f}\": no such file")
                except OSError as e:
                    if not force:
                        raise TclError(str(e))
            return ""
        elif subcmd == "copy":
            force = "-force" in sargs
            paths = [a for a in sargs if a != "-force" and a != "--"]
            if len(paths) >= 2:
                import shutil
                shutil.copy2(paths[0], paths[1])
            return ""
        elif subcmd == "size":
            return str(os.path.getsize(sargs[0]))
        else:
            return ""

    def _cmd_glob(self, interp, args):
        import glob as globmod
        remaining = list(args)
        nocomplain = False
        directory = None
        while remaining and remaining[0].startswith("-"):
            if remaining[0] == "-nocomplain":
                nocomplain = True
            elif remaining[0] == "-directory":
                remaining.pop(0)
                directory = remaining[0] if remaining else "."
            elif remaining[0] == "--":
                remaining.pop(0)
                break
            remaining.pop(0)
        results = []
        for pattern in remaining:
            if directory:
                pattern = os.path.join(directory, pattern)
            results.extend(globmod.glob(pattern))
        if not results and not nocomplain:
            raise TclError(f"no files matched glob pattern")
        return self._to_list(results)

    def _cmd_open(self, interp, args):
        # Return a fake channel ID — we don't fully support file I/O
        # but ORFS scripts use open/puts/close for writing files
        path = args[0]
        mode = args[1] if len(args) > 1 else "r"
        py_mode = {"r": "r", "w": "w", "a": "a", "r+": "r+", "w+": "w+"}
        fh = open(path, py_mode.get(mode, "r"))
        channel = f"file{id(fh)}"
        if not hasattr(self, "_channels"):
            self._channels = {}
        self._channels[channel] = fh
        return channel

    def _cmd_close(self, interp, args):
        if hasattr(self, "_channels") and args[0] in self._channels:
            self._channels[args[0]].close()
            del self._channels[args[0]]
        return ""

    def _cmd_read(self, interp, args):
        if not args:
            raise TclError("wrong # args")
        channel = args[0]
        if hasattr(self, "_channels") and channel in self._channels:
            return self._channels[channel].read()
        # Treat as filename
        try:
            with open(channel) as f:
                return f.read()
        except OSError:
            raise TclError(f"can not read \"{channel}\"")

    def _cmd_gets(self, interp, args):
        if not args:
            raise TclError("wrong # args")
        channel = args[0]
        var = args[1] if len(args) > 1 else None
        if hasattr(self, "_channels") and channel in self._channels:
            line = self._channels[channel].readline()
            if line.endswith("\n"):
                line = line[:-1]
            if var:
                self.variables[var] = line
                return str(len(line)) if line else "-1"
            return line
        return "-1"

    # --- Info commands ---

    def _cmd_info(self, interp, args):
        if not args:
            return ""
        subcmd = args[0]
        if subcmd == "exists":
            return "1" if args[1] in self.variables else "0"
        elif subcmd == "procs":
            pattern = args[1] if len(args) > 1 else "*"
            return self._to_list(list(self.procs.keys()))
        elif subcmd == "commands":
            all_cmds = list(self.commands.keys()) + list(self.procs.keys())
            return self._to_list(all_cmds)
        elif subcmd == "body":
            if args[1] in self.procs:
                return self.procs[args[1]][1]
        elif subcmd == "args":
            if args[1] in self.procs:
                params = self.procs[args[1]][0]
                return self._to_list([p[0] if isinstance(p, list) else p for p in params])
        elif subcmd == "script":
            return self._source_stack[-1] if self._source_stack else ""
        return ""

    def _cmd_array(self, interp, args):
        if not args:
            return ""
        subcmd = args[0]
        arrname = args[1] if len(args) > 1 else ""
        if subcmd == "exists":
            return "1" if arrname in self.arrays else "0"
        elif subcmd == "names":
            if arrname in self.arrays:
                return self._to_list(list(self.arrays[arrname].keys()))
            return ""
        elif subcmd == "get":
            if arrname in self.arrays:
                result = []
                for k, v in self.arrays[arrname].items():
                    result.extend([k, v])
                return self._to_list(result)
            return ""
        elif subcmd == "set":
            pairs = self._parse_list(args[2]) if len(args) > 2 else []
            for i in range(0, len(pairs) - 1, 2):
                self.set_array(arrname, pairs[i], pairs[i + 1])
            return ""
        elif subcmd == "size":
            return str(len(self.arrays.get(arrname, {})))
        return ""

    def _cmd_global(self, interp, args):
        # In our simple scope model, all vars are global
        return ""

    def _cmd_upvar(self, interp, args):
        # Simplified: just alias the variable
        if len(args) >= 2:
            level = "1"
            remaining = list(args)
            if remaining[0].lstrip("-").isdigit() or remaining[0].startswith("#"):
                level = remaining.pop(0)
            while len(remaining) >= 2:
                other = remaining.pop(0)
                local = remaining.pop(0)
                if other in self.variables:
                    self.variables[local] = self.variables[other]
        return ""

    def _cmd_uplevel(self, interp, args):
        if not args:
            return ""
        remaining = list(args)
        if remaining[0].lstrip("-").isdigit() or remaining[0].startswith("#"):
            remaining.pop(0)
        return self._eval_script(" ".join(remaining))

    def _cmd_incr(self, interp, args):
        if not args:
            raise TclError("wrong # args")
        varname = args[0]
        amount = int(args[1]) if len(args) > 1 else 1
        current = int(self.variables.get(varname, "0"))
        result = current + amount
        self.variables[varname] = str(result)
        return str(result)

    def _cmd_append(self, interp, args):
        if not args:
            raise TclError("wrong # args")
        varname = args[0]
        current = self.variables.get(varname, "")
        current += "".join(args[1:])
        self.variables[varname] = current
        return current

    def _cmd_format(self, interp, args):
        if not args:
            return ""
        fmt = args[0]
        vals = args[1:]
        # Convert TCL format to Python format
        # Simple approach: replace %s, %d, %f, %x, %e, %g
        try:
            converted = []
            for v in vals:
                try:
                    if "." in v or "e" in v.lower():
                        converted.append(float(v))
                    else:
                        converted.append(int(v))
                except ValueError:
                    converted.append(v)
            return fmt % tuple(converted)
        except (TypeError, ValueError):
            return fmt

    def _cmd_scan(self, interp, args):
        # Minimal scan implementation
        return "0"

    def _cmd_switch(self, interp, args):
        remaining = list(args)
        exact = True
        while remaining and remaining[0].startswith("-"):
            if remaining[0] == "-exact":
                exact = True
            elif remaining[0] == "-glob":
                exact = False
            elif remaining[0] == "--":
                remaining.pop(0)
                break
            remaining.pop(0)

        if len(remaining) < 2:
            return ""

        string = remaining[0]

        # Two forms: switch string {pattern body pattern body ...}
        # or: switch string pattern body pattern body ...
        if len(remaining) == 2:
            pairs = self._parse_list(remaining[1])
        else:
            pairs = remaining[1:]

        i = 0
        while i < len(pairs) - 1:
            pattern = pairs[i]
            body = pairs[i + 1]
            if pattern == "default" or (exact and string == pattern):
                return self._eval_script(body)
            elif not exact:
                import fnmatch
                if fnmatch.fnmatch(string, pattern):
                    return self._eval_script(body)
            # Handle fall-through: if body is "-", fall to next
            if body == "-" and i + 2 < len(pairs):
                i += 2
                continue
            i += 2
        return ""

    def _cmd_rename(self, interp, args):
        if len(args) != 2:
            raise TclError("wrong # args")
        old, new = args
        if old in self.commands:
            if new:
                self.commands[new] = self.commands[old]
            del self.commands[old]
        elif old in self.procs:
            if new:
                self.procs[new] = self.procs[old]
            del self.procs[old]
        return ""

    def _cmd_eval(self, interp, args):
        return self._eval_script(" ".join(args))

    def _cmd_namespace(self, interp, args):
        if not args:
            return ""
        subcmd = args[0]
        if subcmd == "eval":
            # namespace eval ns body
            if len(args) >= 3:
                return self._eval_script(args[2])
        elif subcmd == "current":
            return "::"
        elif subcmd == "exists":
            return "1"  # all namespaces "exist"
        elif subcmd == "export":
            pass  # no-op
        elif subcmd == "import":
            pass  # no-op
        return ""

    def _cmd_package(self, interp, args):
        # package require name ?version? — just return version
        if args and args[0] == "require":
            return args[2] if len(args) > 2 else "0.0"
        return ""

    def _cmd_variable(self, interp, args):
        # namespace variable — just set it
        i = 0
        while i < len(args):
            name = args[i]
            i += 1
            if i < len(args) and not args[i].startswith("-"):
                self.variables[name] = args[i]
                i += 1
        return ""

    def _cmd_dict(self, interp, args):
        if not args:
            raise TclError("wrong # args")
        subcmd = args[0]
        if subcmd == "create":
            return self._to_list(args[1:])
        elif subcmd == "get":
            d = self._parse_list(args[1])
            keys = args[2:]
            # Navigate nested dict
            for key in keys:
                for i in range(0, len(d) - 1, 2):
                    if d[i] == key:
                        val = d[i + 1]
                        d = self._parse_list(val)
                        break
                else:
                    raise TclError(f"key \"{key}\" not known in dictionary")
            return val if keys else args[1]
        elif subcmd == "set":
            d = self._parse_list(args[1]) if len(args) > 1 else []
            key = args[2] if len(args) > 2 else ""
            value = args[3] if len(args) > 3 else ""
            # Find and replace or append
            found = False
            for i in range(0, len(d) - 1, 2):
                if d[i] == key:
                    d[i + 1] = value
                    found = True
                    break
            if not found:
                d.extend([key, value])
            result = self._to_list(d)
            # If first arg is a variable name, update it
            if len(args) > 1:
                self.variables[args[1]] = result
            return result
        elif subcmd == "exists":
            d = self._parse_list(args[1])
            key = args[2]
            for i in range(0, len(d) - 1, 2):
                if d[i] == key:
                    return "1"
            return "0"
        elif subcmd == "keys":
            d = self._parse_list(args[1])
            keys = [d[i] for i in range(0, len(d) - 1, 2)]
            return self._to_list(keys)
        elif subcmd == "values":
            d = self._parse_list(args[1])
            values = [d[i] for i in range(1, len(d), 2)]
            return self._to_list(values)
        elif subcmd == "size":
            d = self._parse_list(args[1])
            return str(len(d) // 2)
        elif subcmd == "for":
            # dict for {key value} dictValue body
            vars_list = self._parse_list(args[1])
            d = self._parse_list(args[2])
            body = args[3]
            kvar = vars_list[0] if vars_list else "key"
            vvar = vars_list[1] if len(vars_list) > 1 else "value"
            result = ""
            for i in range(0, len(d) - 1, 2):
                self.variables[kvar] = d[i]
                self.variables[vvar] = d[i + 1]
                try:
                    result = self._eval_script(body)
                except TclBreak:
                    break
                except TclContinue:
                    continue
            return result
        return ""

    def _cmd_apply(self, interp, args):
        if not args:
            raise TclError("wrong # args")
        lambda_list = self._parse_list(args[0])
        params = self._parse_list(lambda_list[0]) if lambda_list else []
        body = lambda_list[1] if len(lambda_list) > 1 else ""
        call_args = args[1:]
        # Temporarily register and call
        self.procs["__lambda__"] = (params, body)
        try:
            return self._call_proc("__lambda__", call_args)
        finally:
            del self.procs["__lambda__"]

    def _cmd_after(self, interp, args):
        # No-op for lint
        return ""

    def _cmd_clock(self, interp, args):
        """clock seconds|clicks|format|scan"""
        import time
        if not args:
            return "0"
        subcmd = args[0]
        if subcmd == "seconds":
            return str(int(time.time()))
        elif subcmd == "clicks":
            return str(int(time.time() * 1000000))
        elif subcmd == "milliseconds":
            return str(int(time.time() * 1000))
        elif subcmd == "format":
            ts = int(args[1]) if len(args) > 1 else 0
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        return "0"

    def _cmd_tee(self, interp, args):
        """Handle tee command used in ORFS: tee -o file {commands}"""
        remaining = list(args)
        output_file = None
        append = False
        while remaining:
            if remaining[0] == "-o":
                remaining.pop(0)
                output_file = remaining.pop(0) if remaining else None
            elif remaining[0] == "-a":
                remaining.pop(0)
                output_file = remaining.pop(0) if remaining else None
                append = True
            else:
                break
        # Execute remaining as a command
        result = self._eval_script(" ".join(remaining)) if remaining else ""
        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True) if os.path.dirname(output_file) else None
            mode = "a" if append else "w"
            with open(output_file, mode) as f:
                f.write(result + "\n")
        return result

    # --- Expression evaluation ---

    def _eval_expr(self, expr_str):
        """Evaluate a TCL expression. Returns result as appropriate Python type."""
        # First, substitute variables and commands
        substituted = self._substitute(expr_str)

        # Handle TCL boolean literals
        s = substituted.strip()
        if s.lower() in ("true", "yes", "on"):
            return 1
        if s.lower() in ("false", "no", "off"):
            return 0

        # Replace TCL operators with Python equivalents
        s = re.sub(r'\beq\b', '==', s)
        s = re.sub(r'\bne\b', '!=', s)
        s = s.replace('&&', ' and ')
        s = s.replace('||', ' or ')
        s = s.replace('!', ' not ')
        # Fix double negation from ! replacement
        s = s.replace(' not =', '!=')
        # TCL integer division: use //
        s = re.sub(r'(?<!\/)\/(?!\/)', '//', s)

        # Handle TCL ternary: expr { cond ? a : b }
        # Python eval handles this natively

        # Handle double(x), int(x), etc.
        s = re.sub(r'\bdouble\s*\(', 'float(', s)
        s = re.sub(r'\bround\s*\(', 'round(', s)
        s = re.sub(r'\babs\s*\(', 'abs(', s)
        s = re.sub(r'\bwide\s*\(', 'int(', s)

        # Handle ** power operator (TCL uses **)
        # Python also uses **, so no change needed

        # Handle string equality with quotes
        try:
            # Safe eval with math functions
            result = eval(s, {"__builtins__": {}}, {
                "int": int, "float": float, "round": round, "abs": abs,
                "sqrt": math.sqrt, "pow": pow, "log": math.log,
                "log10": math.log10, "ceil": math.ceil, "floor": math.floor,
                "sin": math.sin, "cos": math.cos, "tan": math.tan,
                "max": max, "min": min,
                "True": 1, "False": 0,
            })
            if isinstance(result, bool):
                return 1 if result else 0
            if isinstance(result, float) and result == int(result) and "." not in s and "e" not in s.lower():
                return int(result)
            return result
        except Exception:
            # If eval fails, return as string
            return s

    def _expr_bool(self, expr_str):
        """Evaluate an expression and return as boolean."""
        result = self._eval_expr(expr_str)
        if isinstance(result, str):
            s = result.strip().lower()
            if s in ("0", "false", "no", "off", ""):
                return False
            if s in ("1", "true", "yes", "on"):
                return True
            try:
                return bool(int(s))
            except ValueError:
                try:
                    return bool(float(s))
                except ValueError:
                    return bool(s)
        return bool(result)
