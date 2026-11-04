<p align="center">
  <a href="https://pdfluent.com/?utm_source=github&utm_medium=referral&utm_campaign=pdfluent_mcp&utm_content=logo">
    <img src="https://pdfluent.com/favicon.svg" width="72" alt="PDFluent logo"/>
  </a>
</p>

<h1 align="center">pdfluent-mcp</h1>

<p align="center"><strong>An MCP server that lets your AI client read, search and fill local PDFs.</strong></p>

<p align="center">
  <a href="https://pypi.org/project/pdfluent-mcp/"><img src="https://img.shields.io/pypi/v/pdfluent-mcp?label=PyPI&color=111111" alt="PyPI"/></a>
  <a href="https://github.com/pdfluent/pdfluent-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/licence-AGPL--3.0%20%7C%20Commercial-111111" alt="Licence: AGPL-3.0 or commercial"/></a>
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-server-111111" alt="MCP server"/></a>
  <a href="https://pdfluent.com"><img src="https://img.shields.io/badge/by-PDFluent-111111" alt="PDFluent"/></a>
</p>

<!-- mcp-name: io.github.pdfluent/pdfluent-mcp -->

An [MCP](https://modelcontextprotocol.io) server for
[PDFluent](https://pdfluent.com). It lets Claude Desktop, Claude Code, Cursor,
VS Code and any other MCP client read a local PDF as markdown, plain text,
tables or positioned blocks, look up its metadata, search it, and fill its
form fields into a new file.

**Runs on your machine, no upload.** It runs over stdio, one process per client,
on the `pdfluent` Python package. Your documents stay on your machine. The
server reads and writes only inside the directories you allow. Your documents
are never uploaded.

<!-- TODO: demo GIF (Claude Desktop asking for the tables of a local PDF). -->

## Quick start

```bash
uvx pdfluent-mcp setup --root ~/Documents
```

This registers a stdio server named `pdfluent` in the user configs of Claude
Desktop, Claude Code, Cursor and Codex, then tells you to restart the clients.
`pipx run pdfluent-mcp setup` works the same way. Without `--root`, file access
relies on client MCP roots or `PDFLUENT_MCP_ROOTS`
([SETUP-001](CLAIMS.md#setup-001), [SETUP-002](CLAIMS.md#setup-002)).

Needs Python 3.10 or later and [`uv`](https://docs.astral.sh/uv/). `uvx`
downloads the server and `pdfluent` on first use and caches them. The balanced
quality tier needs model files; `pdfluent models install` downloads them once.

## Tools

| Tool | What it does | Example prompt |
|---|---|---|
| `extract_markdown` | The document as markdown in reading order: headings, list items and tables. Running heads and page numbers are left out. | "Summarise ~/Documents/report.pdf." |
| `extract_text` | The plain text layer, page by page, each page behind `<!-- page N -->`. | "Give me the raw text of pages 0 to 2 of contract.pdf." |
| `extract_tables` | One entry per table with `page`, `rows` and `header_rows`. | "Pull the tables out of invoice.pdf." |
| `extract_blocks` | Positioned blocks with `kind`, `text`, `page`, `bbox` and `confidence`. Also lists the pages whose text layer is missing. | "List every heading in manual.pdf with its page." |
| `get_metadata` | Page count, title, author, dates, PDF version, encryption, form fields, signatures, bookmarks, and pages with no text layer. | "How many pages does scan.pdf have, and is it encrypted?" |
| `search` | The pages that mention a query, with up to three snippets per page. | "Which pages of policy.pdf mention retention?" |
| `list_form_fields` | Every form field with `name`, `type`, `value` and `page`. | "Which fields does application.pdf have?" |
| `fill_form` | Fills the named fields and writes a new file. The input is never changed. | "Fill application.pdf with my name and address, save as application-filled.pdf." |
| `vision_advice` | One entry per page with `needs_vision` and its reasons. | "Which pages of scan.pdf need a vision model?" |

Page numbers are 0-based in every argument and result.

<details>
<summary>Tool arguments and result details</summary>

| Tool | Returns |
|---|---|
| `extract_markdown(path, pages?, quality?)` | The document as markdown in reading order: headings, list items and tables. Running heads and page numbers are left out. `quality` is `fast` (default) or `balanced`. |
| `extract_text(path, pages?)` | The plain text layer, page by page, each page behind `<!-- page N -->`. |
| `extract_tables(path, pages?)` | `tables`: one entry per table with `page`, `rows` (lists of cell strings) and `header_rows`. |
| `extract_blocks(path, pages?, include_furniture?)` | `blocks`: each with `kind`, `text`, `page`, `bbox` and `confidence`, plus `level`, `ordinal` or table-cell position where they apply. `pages_needing_vision`: the pages whose text layer is missing. |
| `get_metadata(path)` | Page count, title, author, dates, PDF version, encryption, whether the document has form fields, how many signatures and bookmarks it has, and which pages have no text layer. |
| `search(path, query)` | The pages that mention `query`, with up to three snippets per page. |
| `list_form_fields(path)` | Every form field with `name`, `type`, `value` and `page`. |
| `fill_form(path, values, out_path, overwrite?)` | Fills the named fields and writes a new file at `out_path`. The input is never changed; an existing `out_path` is refused unless `overwrite` is true, and a symbolic link there is always refused. |
| `vision_advice(path)` | `advice`: one entry per page with `needs_vision` and its reasons. |

`confidence` is the probability of the learned model that decided a block's
kind; it is `null` where no model decided it, and `null` means unknown, not
low.

</details>

## Install per client

Replace `/path/to/documents` with the directory your PDFs live in.

### Claude Desktop

Add to `claude_desktop_config.json` and restart Claude Desktop:

```json
{
  "mcpServers": {
    "pdfluent": {
      "command": "uvx",
      "args": ["pdfluent-mcp", "--root", "/path/to/documents"]
    }
  }
}
```

<details>
<summary>Config file location and troubleshooting</summary>

macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`,
Windows: `%APPDATA%\Claude\claude_desktop_config.json`.

If Claude Desktop does not find `uvx`, write its full path (`which uvx`) in
`command`.

</details>

### Claude Code

```bash
claude mcp add pdfluent -- uvx pdfluent-mcp --root /path/to/documents
```

<details>
<summary>Project setup for a team, and the Claude skill</summary>

Claude Code also offers its working directory as an MCP root, so inside a
project `claude mcp add pdfluent -- uvx pdfluent-mcp` is enough. For a team,
put this in the project's `.mcp.json`:

```json
{
  "mcpServers": {
    "pdfluent": {
      "type": "stdio",
      "command": "uvx",
      "args": ["pdfluent-mcp"]
    }
  }
}
```

To tell Claude when to reach for these tools, copy `skills/pdfluent` from this
repository to `~/.claude/skills/pdfluent` (every project) or to
`.claude/skills/pdfluent` in one project.

</details>

### Cursor

[Add to Cursor](cursor://anysphere.cursor-deeplink/mcp/install?name=pdfluent&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJwZGZsdWVudC1tY3AiLCItLXJvb3QiLCIvcGF0aC90by9kb2N1bWVudHMiXX0=) (then change `/path/to/documents`), or add to
`~/.cursor/mcp.json` or the project's `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "pdfluent": {
      "type": "stdio",
      "command": "uvx",
      "args": ["pdfluent-mcp", "--root", "/path/to/documents"]
    }
  }
}
```

### VS Code

[Install in VS Code](https://insiders.vscode.dev/redirect/mcp/install?name=pdfluent&config=%7B%22type%22%3A%22stdio%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22pdfluent-mcp%22%2C%22--root%22%2C%22%2Fpath%2Fto%2Fdocuments%22%5D%7D), or from a terminal:

```bash
code --add-mcp '{"name":"pdfluent","type":"stdio","command":"uvx","args":["pdfluent-mcp","--root","/path/to/documents"]}'
```

<details>
<summary>Workspace config</summary>

Or add to `.vscode/mcp.json` in the workspace (note the key is `servers`):

```json
{
  "servers": {
    "pdfluent": {
      "type": "stdio",
      "command": "uvx",
      "args": ["pdfluent-mcp", "--root", "/path/to/documents"]
    }
  }
}
```

</details>

### Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.pdfluent]
command = "uvx"
args = ["pdfluent-mcp", "--root", "/path/to/documents"]
```

One-click install for Cursor and VS Code registers the server with a
placeholder root that you then change.

## Reference

<details>
<summary>Setup command: flags, backups, uninstall</summary>

- `--root DIR` (repeatable) is added to the saved command for each directory you
  name, for example `uvx pdfluent-mcp setup --root ~/Documents`.
- `--dry-run` shows what would change and writes nothing.
- Before it replaces a config file, setup saves the previous file next to it as
  `<name>.pdfluent-backup-<timestamp>` and prints the path.
- `--client claude-desktop|claude-code|cursor|codex` limits it to some clients
  (repeatable).
- `uvx pdfluent-mcp uninstall` (or `setup --uninstall`) removes only the
  `pdfluent` entry, and only when it was written by `pdfluent-mcp` (or with
  `--force`). It does not remove the Python package.

Close the clients before you run setup or uninstall. Files are replaced
atomically, but no portable call lets setup detect a client that saves the same
file in the last instant; a save in that gap can be lost, and where hard links are
unavailable the backup is a plain copy and the gap is wider.

Setup keeps unrelated settings and servers, preserves TOML comments, and
refuses malformed configs and symbolic links. A different existing `pdfluent`
entry is left alone unless you pass `--force`
([SETUP-003](CLAIMS.md#setup-003)). The saved launcher uses the absolute `uvx`
path when found, otherwise the current Python interpreter, which must stay
installed ([SETUP-004](CLAIMS.md#setup-004)).

Config files used: Claude Desktop's platform config (see above), Claude Code's
`~/.claude.json`, Cursor's `~/.cursor/mcp.json`, and Codex's
`~/.codex/config.toml` (`CODEX_HOME` is respected).

</details>

<details>
<summary>Install into your own environment</summary>

```bash
pip install pdfluent-mcp
pdfluent-mcp --root ~/Documents
```

</details>

<details>
<summary>Allowed roots and limits</summary>

The server touches nothing outside its roots. Give them with `--root` (repeat
for more than one), with `PDFLUENT_MCP_ROOTS` (`:`-separated, `;` on
Windows), or let the client offer them: Claude Code sends its working
directory and `--add-dir` directories as MCP roots. A server with no root from
any of these answers every call with a message saying so. Symlinks are
resolved before the check, so a link inside a root cannot point outside it.

A root is as wide as the directory it names. A client that offers `/`, `~`
or a drive as an MCP root widens the server to everything the user can read;
if that is not what you want, start the server with `--root` on the folder
your PDFs live in and keep the client's roots narrow.

Three more limits: `--max-pages` (default 200) is how many pages one call
returns, so a long document is read in windows through `pages` (the engine
still parses the whole document for every window; the cap bounds the output,
not the work); `--max-bytes` (default 100 MiB) is the largest document the
server opens; `--max-output-chars` (default 200000) is the longest result one
call returns, after which it is cut and says so. All three also read from
`PDFLUENT_MCP_MAX_PAGES`, `PDFLUENT_MCP_MAX_BYTES` and
`PDFLUENT_MCP_MAX_OUTPUT_CHARS`.

</details>

<details>
<summary>Claude plugin and data handling</summary>

The repository is also a Claude plugin (`.claude-plugin/plugin.json`). It
bundles the `pdfluent` skill from `skills/` and starts the local MCP server with
`uvx pdfluent-mcp==0.3.0` over stdio, so the plugin runs one pinned PyPI
package and nothing else. A local MCP server loads in Claude Code and in
Cowork sessions on your computer; chat on claude.ai ignores it.

What the plugin does with data: the server reads PDFs only inside the
directories you allow, and writes only the new file that `fill_form` creates
there. It stores nothing, keeps no data after a call returns, and sends nothing
to any other service. The one download is the `pdfluent` package and, if you
choose the balanced tier, the model files from `pdfluent models install`. The
plugin is not aimed at people under 18.

</details>

<details>
<summary>Development</summary>

```bash
pip install -e ".[test]"
pytest
```

The tests start the server over stdio with a real MCP client, call every tool
on the PDFs in `tests/fixtures`, and try to step outside the allowed roots.

</details>

## Licence

The same as the `pdfluent` package it runs on: AGPL-3.0-only, or the PDFluent
Commercial Licence. See `LICENSE` and `LICENSE-COMMERCIAL`. It depends on
`mcp` (MIT).

## Privacy

[Privacy policy](https://pdfluent.com/privacy/)
