# pdfluent-mcp

<!-- mcp-name: io.github.pdfluent/pdfluent-mcp -->

An [MCP](https://modelcontextprotocol.io) server for
[PDFluent](https://pdfluent.com). It lets Claude Desktop, Claude Code, Cursor,
VS Code and any other MCP client read a local PDF as markdown, plain text,
tables or positioned blocks, look up its metadata, search it, and fill its
form fields into a new file.

It runs over stdio, one process per client, on the `pdfluent` Python package.
Your documents stay on your machine. The server reads and writes only inside the
directories you allow. The balanced quality tier needs model files; `pdfluent models
install` downloads them once. Your documents are never uploaded.

<!-- TODO: demo GIF (Claude Desktop asking for the tables of a local PDF). -->

## Tools

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

Page numbers are 0-based in every argument and result. `confidence` is the
probability of the learned model that decided a block's kind; it is `null`
where no model decided it, and `null` means unknown, not low.

## Install

Needs Python 3.10 or later and [`uv`](https://docs.astral.sh/uv/). `uvx`
downloads the server and `pdfluent` on first use and caches them.

```bash
uvx pdfluent-mcp --root ~/Documents
```

Or into an environment of your own:

```bash
pip install pdfluent-mcp
pdfluent-mcp --root ~/Documents
```

### Allowed roots

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

Replace `/path/to/documents` below with the directory your PDFs live in.

### Claude Desktop

Add to `claude_desktop_config.json` (macOS:
`~/Library/Application Support/Claude/claude_desktop_config.json`, Windows:
`%APPDATA%\Claude\claude_desktop_config.json`) and restart Claude Desktop:

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

If Claude Desktop does not find `uvx`, write its full path (`which uvx`) in
`command`.

### Claude Code

```bash
claude mcp add pdfluent -- uvx pdfluent-mcp --root /path/to/documents
```

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

To tell Claude when to reach for these tools, copy `skill/pdfluent` from this
repository to `~/.claude/skills/pdfluent` (every project) or to
`.claude/skills/pdfluent` in one project.

### Cursor

[Add to Cursor](cursor://anysphere.cursor-deeplink/mcp/install?name=pdfluent&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJwZGZsdWVudC1tY3AiLCItLXJvb3QiLCIvcGF0aC90by9kb2N1bWVudHMiXX0=)
(then change `/path/to/documents`), or add to `~/.cursor/mcp.json` or the
project's `.cursor/mcp.json`:

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

[Install in VS Code](https://insiders.vscode.dev/redirect/mcp/install?name=pdfluent&config=%7B%22type%22%3A%22stdio%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22pdfluent-mcp%22%2C%22--root%22%2C%22%2Fpath%2Fto%2Fdocuments%22%5D%7D),
or from a terminal:

```bash
code --add-mcp '{"name":"pdfluent","type":"stdio","command":"uvx","args":["pdfluent-mcp","--root","/path/to/documents"]}'
```

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

### Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.pdfluent]
command = "uvx"
args = ["pdfluent-mcp", "--root", "/path/to/documents"]
```

## Development

```bash
pip install -e ".[test]"
pytest
```

The tests start the server over stdio with a real MCP client, call every tool
on the PDFs in `tests/fixtures`, and try to step outside the allowed roots.

## Licence

The same as the `pdfluent` package it runs on: AGPL-3.0-only, or the PDFluent
Commercial Licence. See `LICENSE` and `LICENSE-COMMERCIAL`. It depends on
`mcp` (MIT).
