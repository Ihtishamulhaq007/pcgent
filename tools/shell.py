"""
pcgent/tools/shell.py

run_shell — the raw escape hatch. Executes a command via the resolved
platform shell (see resolve_shell() below) with cwd forced to
WRITE_ROOT, no output filtering. Deliberate: everything else in this
project enforces boundaries in Python; this tool mostly doesn't, by
explicit choice — except the two checks below.

Shell resolution (replaces the Termux original's hardcoded `bash -c`):
  - Mac/Linux: bash -c "<command>", same as before.
  - Windows: PowerShell by default — `powershell -NoProfile
    -NonInteractive -Command "<command>"` — since that's what's actually
    on every Windows machine out of the box, unlike bash. If the user has
    real bash on PATH (git-bash, WSL, MSYS2) it's auto-preferred instead,
    because most of what the model already knows how to write is bash
    syntax. Override with AGENT_SHELL=powershell or AGENT_SHELL=bash to
    force one or the other regardless of what's detected.

ENABLE_EXTERNAL_WRITE_CONFIRM (on by default), added after real
on-device testing showed the gap in practice: pauses for a real human
y/n when a command looks like it writes outside WRITE_ROOT but inside
SHARED_ROOT — the zone where real files live. This is a heuristic
(permissions.find_external_write_targets), not a hard guarantee like
check_write: relative-path tricks, variable-built paths, and anything
routed through an interpreter other than find -exec can still slip
through unflagged. Reads (ls, cat, find, grep, dir, type, ...) are never
flagged — that stays exactly as unrestricted as it always was.

ENABLE_CATASTROPHIC_CHECK (on by default): a hard block, not a
confirmation prompt, for a handful of patterns that are never a
legitimate build step regardless of location (rm -rf /, mkfs, dd
of=/dev/*, and their cmd.exe/PowerShell equivalents — format c:,
Remove-Item -Recurse -Force C:\\, etc.). It would NOT have caught the
external-write case above — mkdir/cp aren't catastrophic, they're just
out of scope. Two different problems, two different checks. Like
everything else path-based in this project, is_catastrophic_command is
a string-pattern match, not a sandbox — obfuscated or indirect
invocations of the same commands can still slip through. It blocks the
honest/accidental case, not a determined adversarial one.

ENABLE_NETWORK_EGRESS_CONFIRM (on by default), added after a real
session sent personal audio to a third-party transcription API with no
confirmation gate at all. Same shape as the external-write check: pauses
for human y/n when a command looks like it sends data off-device
(curl/wget/ssh/scp/nc, Invoke-WebRequest/Invoke-RestMethod, an inline
python one-liner importing requests/urllib/socket/etc, or an inline
node one-liner calling fetch/http.request/net.connect/etc — see
permissions.find_network_egress_targets). Deliberately does not try to
distinguish "just fetching a URL" from "uploading local content" — both
are flagged, because the read/write distinction that matters for the
write gate doesn't hold here: a GET can still leak local data via a
query string or header built from file contents. Heuristic, not a
sandbox — routes around it exactly like the write check can be routed
around.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from ..config import Config
from ..permissions import (
    find_external_write_targets,
    find_network_egress_targets,
    is_catastrophic_command,
)
from .base import Tool, ToolResult

ENABLE_CATASTROPHIC_CHECK = True
ENABLE_EXTERNAL_WRITE_CONFIRM = True
ENABLE_NETWORK_EGRESS_CONFIRM = True
_TIMEOUT_SECONDS = 300  # a single command running this long is almost certainly stuck


def resolve_shell() -> tuple[str, list[str]]:
    """Returns (label, argv_prefix) — argv_prefix is the command list to
    prepend before the user's command string, e.g. ["bash", "-c"] or
    ["powershell", "-NoProfile", "-NonInteractive", "-Command"].

    AGENT_SHELL env var forces a choice ("bash" or "powershell").
    Otherwise: non-Windows always uses bash (matches the original
    Termux behavior). On Windows, bash is preferred if it's actually on
    PATH (git-bash/WSL/MSYS2 users get familiar bash syntax); PowerShell
    is the fallback since it's present on every Windows install."""
    forced = os.environ.get("AGENT_SHELL", "").strip().lower()
    if forced == "bash":
        return "bash", ["bash", "-c"]
    if forced == "powershell":
        return "powershell", ["powershell", "-NoProfile", "-NonInteractive", "-Command"]

    if sys.platform != "win32":
        return "bash", ["bash", "-c"]

    if shutil.which("bash"):
        return "bash", ["bash", "-c"]
    return "powershell", ["powershell", "-NoProfile", "-NonInteractive", "-Command"]


class RunShellTool(Tool):
    name = "run_shell"

    def __init__(self):
        self._shell_label, self._shell_prefix = resolve_shell()

    @property
    def description(self) -> str:
        return (
            f"Run a shell command via {self._shell_label}, cwd forced to WRITE_ROOT. Commands matching a "
            "small hardcoded catastrophic-pattern list (rm -rf /, mkfs, dd of=/dev/*, format c:, "
            "Remove-Item -Recurse -Force C:\\, etc.) are refused outright — this is a pattern match, not "
            "a sandbox, and can be routed around. If the command looks like it writes outside WRITE_ROOT "
            "(mkdir/cp/mv/rm/dd/tee/redirects/find -exec, or del/copy/move/New-Item/Remove-Item targeting "
            "an external path), or looks like it sends data off-device (curl/wget/ssh/scp/nc, "
            "Invoke-WebRequest/Invoke-RestMethod, an inline python snippet using requests/urllib/socket/etc, "
            "or an inline node snippet using fetch/http.request/net.connect/etc), it pauses for human "
            "confirmation first — call again with confirmed=true only after that's been granted. "
            "IMPORTANT: relative paths here "
            "resolve against WRITE_ROOT (this tool's cwd) — a DIFFERENT base than "
            "read_file/write_file/list_directory/etc., which resolve relative paths against READ_ROOT "
            "instead. The same relative name (e.g. 'core') can mean two different real locations "
            "depending on which tool you used it with. When in doubt, use absolute paths, or run "
            f"'pwd' (bash) / 'Get-Location' (PowerShell) first."
        )

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": f"Shell command to run via {self._shell_label}.",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": (
                            "Leave false. Only set true after a human has explicitly approved a "
                            "flagged external-write command — controller.py handles this, not you."
                        ),
                    },
                },
                "required": ["command"],
            },
        }

    def run(self, config: Config, command: str, confirmed: bool = False, **kwargs) -> ToolResult:
        if ENABLE_CATASTROPHIC_CHECK and is_catastrophic_command(command):
            return ToolResult.fail(
                f"Refused: {command!r} matches a catastrophic-command pattern."
            )

        if ENABLE_EXTERNAL_WRITE_CONFIRM and not confirmed:
            external_targets = find_external_write_targets(command, config)
            if external_targets:
                return ToolResult.needs_confirmation(
                    f"This command looks like it writes outside WRITE_ROOT: {', '.join(external_targets)}\n"
                    f"Command: {command}",
                    external_targets=external_targets,
                    command=command,
                )

        if ENABLE_NETWORK_EGRESS_CONFIRM and not confirmed:
            network_targets = find_network_egress_targets(command)
            if network_targets:
                return ToolResult.needs_confirmation(
                    f"This command looks like it sends data off-device: {', '.join(network_targets)}\n"
                    f"Command: {command}",
                    network_targets=network_targets,
                    command=command,
                )
        try:
            proc = subprocess.run(
                [*self._shell_prefix, command],
                cwd=config.write_root,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return ToolResult.fail(f"Command timed out after {_TIMEOUT_SECONDS}s: {command!r}")
        except OSError as e:
            return ToolResult.fail(
                f"Could not run command via {self._shell_label}: {e}\n"
                f"({self._shell_label} not found on PATH — set AGENT_SHELL=bash or AGENT_SHELL=powershell "
                "to force the other one, or install the missing shell.)"
            )

        output = proc.stdout
        if proc.stderr:
            output += ("\n--- stderr ---\n" if output else "") + proc.stderr

        if proc.returncode == 0:
            return ToolResult.ok(output, exit_code=0, command=command)
        return ToolResult.fail(output or f"exit code {proc.returncode}", exit_code=proc.returncode, command=command)


if __name__ == "__main__":
    from ..config import load_config
    from .registry import ToolRegistry

    config = load_config()
    registry = ToolRegistry()
    tool = RunShellTool()
    registry.register(tool)
    print(f"Resolved shell: {tool._shell_label} {tool._shell_prefix}")
    print()

    pwd_cmd = "pwd" if tool._shell_label == "bash" else "Get-Location"
    print(f"{pwd_cmd} (should print write_root) ->", registry.call("run_shell", config, command=pwd_cmd))
    print()

    if tool._shell_label == "bash":
        print(
            "simple success ->",
            registry.call(
                "run_shell", config, command="echo hello && mkdir -p shell_check && echo done > shell_check/out.txt"
            ),
        )
    else:
        print(
            "simple success ->",
            registry.call(
                "run_shell", config,
                command="echo hello; New-Item -ItemType Directory -Force shell_check | Out-Null; "
                        "'done' | Out-File shell_check/out.txt",
            ),
        )

    print()
    print("catastrophic check is ON by default — this SHOULD be refused right now:")
    bad = "rm -rf /" if tool._shell_label == "bash" else "Remove-Item -Recurse -Force C:\\"
    print(registry.call("run_shell", config, command=bad))

    print()
    print("network-egress check is ON by default — this SHOULD pause for confirmation:")
    net = "curl -s https://example.com" if tool._shell_label == "bash" else "Invoke-WebRequest https://example.com"
    print(registry.call("run_shell", config, command=net))
