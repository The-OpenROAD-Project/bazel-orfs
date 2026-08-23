#!/usr/bin/env python3
import sys
import json
import re


def process_request(payload):
    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    args = tool_call.get("args", {})

    def has_bazel_folder(path):
        if not path: return False
        # Do not match the repository name (e.g. bazel-orfs), only the output directory symlinks
        return re.search(r'(^|/)bazel-(out|bin|testlogs)(/|$)', str(path)) is not None

    def has_cache_folder(path):
        if not path: return False
        return re.search(r'(^|/)\.cache(/|$)', str(path)) is not None

    def is_tmp_folder(path):
        if not path: return False
        # Matches /tmp, /tmp/..., but NOT ./tmp, /something/tmp
        return re.match(r'^/tmp(/|$)', str(path)) is not None

    def get_redirection_message(path_or_cmd):
        content = str(path_or_cmd).lower()
        if 'bazel-testlogs' in content:
            return "Do not read raw bazel-testlogs directly to avoid context explosion. Extract failures using a targeted script."
        if 'netlist' in content or 'bazel-bin' in content:
            return "Do not grep raw generated files in bazel-bin or netlists to avoid context explosion."
        if 'cache' in content or 'external' in content:
            return "Do not spelunk in bazel cache. Clone dependencies into ./tmp if you need to inspect or patch them."
        return "Spelunking in bazel-* or .cache output directories is forbidden as it causes context explosion and wastes time."

    # 1. Block bazelisk clean / bazel clean / tmp usage in run_command
    if tool_name == "run_command":
        cmd = args.get("CommandLine", "")
        cwd = args.get("Cwd", "")

        if re.search(r'\bbazel(isk)?\s+clean\b', cmd):
            return {
                "decision":
                "deny",
                "reason":
                "bazelisk clean and bazel clean => verboten, protects bazel cache."
            }

        if re.search(
                r'(?:^|&&|;|\|\||\||\n)\s*git\s+(checkout|switch|rebase|cherry-pick|merge|reset|pull)\b',
                cmd):
            clean_cmd = re.sub(r'\borigin/(master|main)\b', '', cmd)
            if re.search(r'(?<![\w\-])(master|main)(?![\w\-])', clean_cmd):
                return {
                    "decision":
                    "deny",
                    "reason":
                    "git checkout/rebase/cherry-pick/merge/reset/pull master => verboten. Always use origin/master directly (detached HEAD) or use git worktree."
                }

        if re.search(
                r'\b(find|grep|tree|ls|fd|rg|cat|head|tail|less)\b.*(\bbazel-(out|bin|testlogs)\b|\.cache\b)',
                cmd) or has_bazel_folder(cwd) or has_cache_folder(cwd):
            msg = get_redirection_message(cmd + " " + cwd)
            return {"decision": "deny", "reason": msg}

        if re.search(r'(^|\s)/tmp\b', cmd) or is_tmp_folder(cwd):
            return {
                "decision": "deny",
                "reason":
                "Using /tmp is forbidden. Always use ./tmp."
            }

    # 2. Block spelunking and /tmp via native tools
    elif tool_name == "grep_search":
        path = args.get("SearchPath", "")
        if has_bazel_folder(path) or has_cache_folder(path):
            return {
                "decision": "deny",
                "reason": get_redirection_message(path)
            }
        if is_tmp_folder(path):
            return {
                "decision": "deny",
                "reason":
                "Using /tmp is forbidden. Always use ./tmp."
            }

    elif tool_name == "list_dir":
        path = args.get("DirectoryPath", "")
        if has_bazel_folder(path) or has_cache_folder(path):
            return {
                "decision": "deny",
                "reason": get_redirection_message(path)
            }
        if is_tmp_folder(path):
            return {
                "decision": "deny",
                "reason":
                "Using /tmp is forbidden. Always use ./tmp."
            }

    elif tool_name in [
            "view_file", "write_to_file", "replace_file_content",
            "multi_replace_file_content"
    ]:
        # various tools use different arg names for the file path
        path = args.get("AbsolutePath") or args.get("TargetFile") or ""
        if has_bazel_folder(path) or has_cache_folder(path):
            return {
                "decision": "deny",
                "reason": get_redirection_message(path)
            }
        if is_tmp_folder(path):
            return {
                "decision": "deny",
                "reason":
                "Using /tmp is forbidden. Always use ./tmp."
            }

    return {"decision": "allow"}


def main():
    try:
        input_data = sys.stdin.read()
        if not input_data.strip():
            print(json.dumps({"decision": "allow"}))
            return

        payload = json.loads(input_data)
        response = process_request(payload)
        print(json.dumps(response))

    except Exception as e:
        # Failsafe allow so we don't break the agent on error
        print(
            json.dumps({
                "decision": "allow",
                "reason": f"Hook error: {str(e)}"
            }))


if __name__ == "__main__":
    main()
