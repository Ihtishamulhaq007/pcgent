#!/usr/bin/env python3
"""
install.py — cross-platform setup for pcgent.

Replaces the old Termux install.sh (which relied on `pkg`, `termux-setup-
storage`, and appending to ~/.bashrc — none of which exist on Windows,
and the shell-rc part is unreliable across Mac/Linux shells too). This
does the same job with only the standard library, so it runs identically
under `python install.py` on Windows, macOS, or Linux.

What it does:
  1. Checks git is on PATH (needed for the git_status/git_diff tools).
  2. Checks a shell is available to run commands through (bash, or on
     Windows, PowerShell — see pcgent/tools/shell.py).
  3. Prompts for your Gemini API key and lets you pick a model, fetched
     live from the API (same approach as before).
  4. Writes both into a .env file at the repo root — NOT a shell rc file.
     config.py loads .env automatically on startup. This sidesteps the
     fact that .bashrc/.zshrc/PowerShell's $PROFILE are all different
     files in different formats depending on OS and shell.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
ENV_PATH = REPO_DIR / ".env"
DEFAULT_MODEL = "gemini-3.5-flash-lite"


def step(n: int, total: int, label: str) -> None:
    print(f"\n== {n}/{total}: {label} ==")


def check_git() -> None:
    if shutil.which("git"):
        print("git found on PATH.")
        return
    print("git not found on PATH.")
    print("  Windows: https://git-scm.com/download/win")
    print("  macOS:   xcode-select --install   (or https://git-scm.com/download/mac)")
    print("  Linux:   your package manager, e.g. apt install git / dnf install git")
    print("git_status/git_diff will fail until this is installed; everything else still works.")


def check_shell() -> str:
    if sys.platform == "win32":
        if shutil.which("bash"):
            return "bash (found — git-bash/WSL/MSYS2 detected, will be used by default)"
        if shutil.which("powershell"):
            return "PowerShell (default on Windows)"
        print("Neither bash nor PowerShell found on PATH — run_shell will not work.")
        return "none found"
    else:
        if shutil.which("bash"):
            return "bash"
        print("bash not found on PATH — run_shell will not work until it's installed.")
        return "none found"


def read_existing_env() -> dict:
    values = {}
    if ENV_PATH.is_file():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def write_env(values: dict) -> None:
    lines = [f"{k}={v}" for k, v in values.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fetch_models(api_key: str) -> list[str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return []
    names = []
    for m in data.get("models", []):
        name = m.get("name", "").removeprefix("models/")
        if not name:
            continue
        low = name.lower()
        if ("flash" in low or "pro" in low) and not any(
            bad in low for bad in ("embedding", "aqa", "image", "imagen", "video", "veo", "tts", "vision", "live", "robotics")
        ):
            names.append(name)
    return sorted(set(names))


def main() -> int:
    total = 4
    print("pcgent setup")

    step(1, total, "Checking git")
    check_git()

    step(2, total, "Checking shell")
    shell_status = check_shell()
    print(f"Shell for run_shell: {shell_status}")

    step(3, total, "Gemini config")
    existing = read_existing_env()

    api_key = existing.get("GEMINI_API_KEY")
    if api_key:
        print("Using existing GEMINI_API_KEY from .env.")
    else:
        api_key = input("Paste your Gemini API key (from https://aistudio.google.com/apikey): ").strip()

    model = existing.get("GEMINI_MODEL")
    if model:
        print(f"GEMINI_MODEL already set in .env ({model}), leaving it as-is.")
    else:
        print("Fetching available Gemini models...")
        models = fetch_models(api_key)
        if not models:
            print("Couldn't fetch the model list (check your key/network). Using a safe default.")
            model = DEFAULT_MODEL
        else:
            print("\nAvailable models:")
            default_idx = 1
            for i, m in enumerate(models, start=1):
                tag = "   <-- recommended: fast and reliable" if m == DEFAULT_MODEL else ""
                if m == DEFAULT_MODEL:
                    default_idx = i
                print(f"  {i}) {m}{tag}")
            choice = input(f"\nPick a number [default: {default_idx}]: ").strip()
            try:
                idx = int(choice) if choice else default_idx
                model = models[idx - 1]
            except (ValueError, IndexError):
                model = DEFAULT_MODEL
        print(f"Selected: {model}")

    write_env({**existing, "GEMINI_API_KEY": api_key, "GEMINI_MODEL": model})

    step(4, total, "Done")
    print("Setup complete. Run the agent with:")
    print()
    print(f'  cd "{REPO_DIR}"')
    print('  python -m pcgent.main --goal "your goal here"')
    print()
    print("API key and model are stored in .env — do not commit this file (see .gitignore).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
