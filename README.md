# pcgent

An autonomous coding agent that runs on Windows, macOS, or Linux, using the
Gemini API as the model backend. Ported from Androgent (the Termux/Android
original). You give it a goal in plain English; it plans, calls tools
(read/write files, run shell commands, git, grep) in a loop, and stops when it
believes the goal is done or it gets stuck — pausing for your confirmation at
anything risky along the way.

## How it works

```
you (--goal) → main.py → Controller loop → Gemini (model.py)
                              │                  │
                              │          "call tool X with args Y"
                              ▼                  ▼
                         ToolRegistry ──────► Tool.run()
                              │
                    permissions.py checks every
                    path before any read/write
```

**The loop (`controller.py`)** repeatedly: sends the conversation + goal to
Gemini, gets back a tool call, executes it, feeds the result back, repeats.
It stops when the model calls `finish_task` and you confirm, when you decline
to extend the iteration budget, or on Ctrl+C.

**Tools available to the model:**

| Tool | Does |
|---|---|
| `read_file` / `write_file` / `append_file` | File I/O, routed through permission checks |
| `list_directory` / `find_files` / `grep` | Explore the filesystem |
| `stage_file` / `promote_file` | Edit a copy first, then promote it into place |
| `delete_file` | Remove a file |
| `run_shell` | Execute a shell command (bash on Mac/Linux; PowerShell by default on Windows, bash if git-bash/WSL is on PATH — see `tools/shell.py`) |
| `git_status` / `git_diff` | Read-only git inspection |
| `finish_task` | Signal the goal is done or the agent is stuck — always pauses for human confirmation |

**Safety boundaries:**
- `permissions.py` checks every file path before any read or write against
  `WRITE_ROOT` — the agent can't casually write outside its sandboxed folder.
- `run_shell` has three checks **on by default**: a hard block on a small
  catastrophic-command pattern list, a confirmation pause for commands that
  look like they write outside `WRITE_ROOT`, and a confirmation pause for
  commands that look like they send data off-device. All three are heuristics,
  not a sandbox — see `WARNING.md`.
- Anything flagged `requires_confirmation` (like `promote_file`, `delete_file`)
  never executes without an explicit y/n from you at the terminal, no matter
  what the model asks.
- Sessions are logged to disk — a JSONL audit trail plus a human-readable log
  per run — so you can review exactly what happened.

**Read `WARNING.md` before pointing this at anything you care about.** The
security boundary on a PC is weaker than it was on Termux/Android — see why
there.

**Sessions** are identified by a timestamp ID and can be resumed with
`--resume SESSION_ID`, continuing the exact prior conversation history instead
of starting fresh.

## Dependencies

None beyond the standard library — no `pip install` needed for the agent code
itself (`urllib` handles the Gemini API calls).

You do need:

| Requirement | Why |
|---|---|
| Python 3.10+ | Runs the agent |
| `git` | Used by the agent's read-only git tools, and to clone/manage this repo |
| Gemini API key | Free tier at https://aistudio.google.com/apikey |
| A shell on PATH | bash (Mac/Linux, or Windows via git-bash/WSL) or PowerShell (Windows default) |

## Setup

```bash
git clone <your-pcgent-repo-url>
cd pcgent
python install.py
```

`install.py` checks for git and a usable shell, then prompts once for your
Gemini API key and model, and saves both to a `.env` file at the repo root
(gitignored) — loaded automatically by `config.py` on every run. No shell rc
file editing, so this works the same way on Windows, macOS, and Linux.

## Run

From the repo root (the folder containing this package):

```bash
python -m pcgent.main --goal "your goal here"
```

Resume a previous session:

```bash
python -m pcgent.main --goal "your goal here" --resume 2026-09-27_120000_your-goal
```

## Notes

- Files the agent writes land under `<your home directory>/pcgent` by default.
- Override the root with `AGENT_SHARED_ROOT` and the workspace folder name
  with `AGENT_WORKSPACE_DIRNAME` (both in `.env` or your environment).
- Force a specific shell for `run_shell` with `AGENT_SHELL=bash` or
  `AGENT_SHELL=powershell`, overriding auto-detection.
- Logs (audit + human-readable) are written per-session and gitignored.
