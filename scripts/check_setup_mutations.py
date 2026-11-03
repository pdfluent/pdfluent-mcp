"""Prove setup acceptance tests fail when required behavior is removed.

Only disposable copies are mutated. The working tree stays untouched.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = [
    ("registration", "setup.py", "servers[SERVER_NAME] = entry", "pass", "test_client_format_roundtrip"),
    ("codex-format", "setup.py", '"mcp_servers" if is_toml', '"wrong_servers" if is_toml', "test_client_format_roundtrip[codex]"),
    ("dry-run", "setup.py", "and not args.dry_run:", ":", "test_missing_config_dry_run_install_uninstall"),
    ("uninstall", "setup.py", "del servers[SERVER_NAME]", "pass", "test_client_format_roundtrip"),
    ("desktop-path", "setup.py", "Application Support/Claude/", "Application Support/Wrong/", "test_platform_paths"),
    ("claude-code-path", "setup.py", ' / ".claude.json"', ' / "wrong.json"', "test_platform_paths"),
    ("cursor-path", "setup.py", ' / ".cursor/mcp.json"', ' / "wrong/mcp.json"', "test_platform_paths"),
    ("dispatch", "cli.py", '{"setup", "uninstall"}', '{"uninstall"}', "test_client_format_roundtrip"),
]


def main():
    for name, module, old, new, test in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix="pdfluent-setup-mutation-") as directory:
            scratch = Path(directory)
            shutil.copytree(ROOT / "pdfluent_mcp", scratch / "pdfluent_mcp", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy(ROOT / "tests/test_setup.py", scratch / "test_setup.py")
            path = scratch / "pdfluent_mcp" / module
            source = path.read_text(encoding="utf-8")
            if source.count(old) != 1:
                raise SystemExit(f"{name}: expected exactly one mutation site")
            path.write_text(source.replace(old, new), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"test_setup.py::{test}"],
                cwd=scratch, env=dict(os.environ, PYTHONPATH=str(scratch), PYTHONDONTWRITEBYTECODE="1"),
                capture_output=True, text=True,
            )
            # Exit 1 is an actual failed test, not a collection/usage error.
            if result.returncode != 1 or "FAILED" not in result.stdout:
                print(result.stdout, result.stderr)
                raise SystemExit(f"{name}: mutation survived or tests did not run (exit {result.returncode})")
            print(f"{name}: rejected (pytest exit 1)")
    print(f"{len(MUTATIONS)} setup mutations rejected")


if __name__ == "__main__":
    main()
