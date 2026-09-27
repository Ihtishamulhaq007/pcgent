# WARNING — Autonomous Agent Shell Security (pcgent)

## Current check status

`run_shell` has three checks, **all ON by default** in this codebase
(`ENABLE_CATASTROPHIC_CHECK`, `ENABLE_EXTERNAL_WRITE_CONFIRM`,
`ENABLE_NETWORK_EGRESS_CONFIRM` in `tools/shell.py`). This differs from the
original Androgent `WARNING.md`, which described a state where those checks
were disabled — that text was stale relative to the actual code even in the
original repo. Verify their status yourself in `tools/shell.py` before relying
on this document; if someone has flipped any of the three off, the relevant
section below applies.

## The bigger difference from Termux: there is no app sandbox here

This is the part worth reading even if you already read the original warning.

On Termux/Android, `run_shell` executed with **the Termux app's own sandboxed
permissions** — a real OS-level boundary independent of anything in this
codebase. Even with every internal check disabled, the blast radius was capped
by what Android let the Termux process touch.

On Windows/macOS/Linux, **there is no equivalent boundary**. `run_shell` runs
with the full permissions of whatever user account is running Python — your
user account, most likely. That means:

- Full read/write access to every file your user account can touch, not just
  a sandboxed app's storage — your entire home directory, Documents, other
  drives, cloud-sync folders (OneDrive/iCloud/Dropbox), everything.
- No OS-level barrier stopping it from reading SSH keys, browser-saved
  credentials, other apps' config files, or `.env` files in other projects.
- On Windows specifically, if you ever run the agent from an Administrator
  terminal, the shell commands inherit that elevation too — don't do this.

**The practical upshot: `WRITE_ROOT` and the three `run_shell` checks are the
entire security boundary on a PC.** There is no second layer behind them the
way Android's sandbox was a second layer behind Termux's own checks. Treat
this codebase's checks as load-bearing, not a redundant extra.

## What the three checks do and don't catch

- **Catastrophic-command check** — hard refusal for a short pattern list
  (`rm -rf /`, `format c:`, `Remove-Item -Recurse -Force C:\`, etc., see
  `permissions.py`). String-pattern match, not a parser — trivially routed
  around (`r'm -rf /'`, a base64-encoded command piped to the interpreter,
  a script file that does the same thing, etc.).
- **External-write confirmation** — pauses for y/n if a command looks like it
  writes outside `WRITE_ROOT`. Heuristic: relative-path tricks, paths built
  from variables, and anything not matching the known write-command list
  (`mkdir`/`cp`/`New-Item`/etc.) slip through unflagged.
- **Network-egress confirmation** — pauses for y/n if a command looks like it
  sends data off-device. Same tier of protection — a network call through a
  tool or API not on the recognized list slips through.

None of the three is a sandbox. All three are speed bumps for the honest or
accidental case, not a boundary against a determined adversarial prompt
injection or a genuinely compromised model.

## If you disable any of the three checks

Read the original Androgent `WARNING.md` reasoning — it still applies, and
applies harder here because of the missing app-sandbox layer above. Assume
`run_shell` is equivalent to giving an untrusted program arbitrary code
execution as your user account, with access to your secrets, your other
projects, and (if network egress checking is off) the ability to exfiltrate
any of it.

## Recommended practice

1. Keep all three checks on unless you have a specific, temporary reason not
   to, and turn them back on immediately after.
2. Don't run this from an elevated/Administrator/root terminal.
3. Consider running it inside a container, VM, or a dedicated low-privilege
   user account if you want a real second boundary back — that's the
   PC-native equivalent of what Android's app sandbox gave the Termux
   original for free.
4. Keep secrets (API keys, SSH keys, browser profiles) out of `AGENT_SHARED_ROOT`
   where practical.
