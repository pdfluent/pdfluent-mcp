# Changelog

## 0.3.0

- Add `pdfluent-mcp setup`: registers the server in the user configs of Claude
  Desktop, Claude Code, Cursor and Codex. Options: `--root DIR` (repeatable),
  `--client`, `--dry-run`, `--force`.
- Add `pdfluent-mcp uninstall` (and `setup --uninstall`): removes only the
  `pdfluent` entry.
- Setup keeps unrelated settings and TOML comments, writes atomically, refuses
  malformed configs and symbolic links, and leaves a different existing
  `pdfluent` entry alone unless `--force` is given.
- Setup saves a timestamped backup of each config file before replacing it,
  re-checks the file just before the swap, and uninstall removes only an entry
  that `pdfluent-mcp` wrote unless `--force` is given.
- Add `tomlkit` as a dependency.
- Add a Claude plugin manifest (`.claude-plugin/plugin.json`) that bundles the
  skill and starts the server with `uvx pdfluent-mcp==0.3.0`.

## 0.2.0

- See the git history; earlier releases were not recorded in this file.
