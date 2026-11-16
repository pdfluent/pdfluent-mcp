# Installing pdfluent-mcp (for agents such as Cline)

pdfluent-mcp is a local MCP server over stdio. It needs Python 3.10 or later and
[`uv`](https://docs.astral.sh/uv/). No API key and no account.

1. Ask the user which folder their PDFs live in. The server only reads and
   writes inside folders it is given.
2. Add this server to the MCP settings, replacing `/path/to/documents` with that
   folder:

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

3. If the client cannot find `uvx`, write its full path (`which uvx`, or
   `where uvx` on Windows) in `command`.
4. Check the install by calling `get_metadata` on a PDF inside the folder.

The default quality tier needs nothing else. The `balanced` tier needs model
files, which the user installs once with `pdfluent models install`.
