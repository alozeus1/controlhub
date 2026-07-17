#!/usr/bin/env python3
"""
Large-file / archive repository-policy guard (P0-2 follow-up).

Fails if any git-tracked file exceeds the size threshold or matches a banned
archive/secret pattern. Runs in CI so a future `code.zip`-style blob is blocked
at the gate.
"""
import subprocess
import sys

MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BANNED_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".pem", ".key", ".p12", ".pfx")
ALLOW = {"admin-ui/package-lock.json", "package-lock.json"}


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True).stdout
    return [f for f in out.split("\0") if f]


def main():
    problems = []
    for f in tracked_files():
        if f in ALLOW:
            continue
        if f.lower().endswith(BANNED_SUFFIXES):
            problems.append(f"banned artifact tracked: {f}")
            continue
        try:
            size = subprocess.run(["git", "cat-file", "-s", f":{f}"],
                                  capture_output=True, text=True).stdout.strip()
            if size and int(size) > MAX_BYTES:
                problems.append(f"file too large ({int(size)//1024} KB > 5 MB): {f}")
        except Exception:
            pass
    if problems:
        print("REPOSITORY POLICY VIOLATIONS:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("OK: no oversized or banned artifacts tracked.")


if __name__ == "__main__":
    main()
