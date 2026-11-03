# Setup claims

This file records the claims introduced with the setup command.

## SETUP-001

Setup registers a stdio server named `pdfluent` in four user client configs.
Evidence: `tests/test_setup.py::test_client_format_roundtrip`,
`test_all_default_and_selection`, `test_platform_paths`, `test_config_overrides`.
Client formats and paths: [Claude Desktop](https://modelcontextprotocol.io/quickstart/user),
[Claude Code](https://code.claude.com/docs/en/mcp),
[Cursor](https://cursor.com/docs/mcp),
[Codex](https://developers.openai.com/codex/mcp/). Checked 2026-11-03.

## SETUP-002

Setup validates and forwards repeated explicit roots. With no explicit roots,
the existing server's client roots and environment behavior applies.
Evidence: `test_multiple_roots`, `test_invalid_root_writes_nothing`,
`test_missing_config_dry_run_install_uninstall`; server `configure` and `_roots`.

## SETUP-003

Client selection, dry-run, idempotent setup, conflict refusal with explicit
replacement, and uninstall preserve unrelated settings. Malformed configs and
symlink config files are refused. TOML comments survive edits. Uninstall removes
the entry without uninstalling the package.
Evidence: `test_client_format_roundtrip`, `test_conflict_requires_force`,
`test_missing_config_dry_run_install_uninstall`, `test_all_default_and_selection`,
`test_bad_config_preflight_writes_nothing`, `test_permissions_and_symlink`.

## SETUP-004

The launcher prefers an absolute uvx path, falling back to the current Python
interpreter and `-m pdfluent_mcp`. A fallback interpreter must remain installed.
Evidence: `test_client_format_roundtrip`, `test_fallback_launcher`.
