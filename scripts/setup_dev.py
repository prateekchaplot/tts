#!/usr/bin/env python3
"""Cross-platform, idempotent developer environment setup."""

import subprocess
import sys


def run(cmd):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    run(["uv", "sync", "--group", "dev"])
    run(["uv", "run", "pre-commit", "install"])
    print("Dev environment ready. Hooks installed; use --no-verify to bypass.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
