---
name: pdfluent-extract
description: Use the PDFluent Extract API tools to turn PDFs into markdown, text, tables, chunks or structured fields, to search a document, and to check what a call costs in credits. Use when a task needs the content of a PDF sent to the hosted service, or when the user asks what an extraction call will cost.
---

# PDFluent Extract API

The `pdfluent-extract` MCP server calls the PDFluent Extract API at
`https://api.pdfluent.com/mcp/extract`. Each API operation is one tool. The
tool name is the operation id with dots turned into underscores, for example
`extract_markdown` or `extract_tables`. Files go in as base64 in `files`; the
operation's options go in `options`. The full tool list is at
https://pdfluent.com/docs/api/mcp/.

This server holds the extraction tools only. To merge, split, convert or fill a
PDF, use the `pdfluent-pdf` plugin.

The documents you send leave this machine. If the user wants a document to stay
local, use the local `pdfluent` MCP server (`pdfluent-mcp`) instead, and say so
before sending anything.

## Setup

Claude Code asks for the PDFluent API key when the plugin is enabled and keeps
it out of the conversation. If a call answers 401, the key is missing or
invalid: tell the user to create a key in the PDFluent console and enter it
again in the plugin settings. Do not ask the user to paste the key into the
chat.

## Which tool

- **Read or quote a PDF**: `extract_markdown`. Headings, lists and tables keep
  their shape. Pass `options.pages` (1-based) to read a window of a long
  document.
- **Table data as rows**: `extract_tables`.
- **Plain text layer**: `extract_text`.
- **Chunks for retrieval**: `extract_chunks`, or `extract_embeddings` for
  vectors.
- **Fields into a schema**: `extract_schema`.
- **Images inside the PDF**: `extract_images`.
- **Elements in the shape of other partitioners**: `partition`, or
  `compat_unstructured_general` for a drop-in for that API.
- **Classify, ask or summarize**: `ai_classify`, `ai_query`, `ai_summarize`.
- **Find where something is mentioned**: `search`, then read only those pages.
- **Know what a file is before spending credits**: `info` (page count, whether
  it is encrypted) first, then pick the quality.
- **Scanned pages**: `extract_markdown` with `options.quality` set to `auto`.

Tools that only read declare `readOnlyHint: true`. Ask the user before calling
a tool that spends a large number of credits.

## Cost in credits

Calls are paid from a prepaid credit balance. Every response carries
`x-pdfluent-pages` and `x-pdfluent-credits`; report them back after a call.

- Extraction costs credits per page by quality, as of 22 November 2026: `fast`
  1, `balanced` 2, `auto` 3, `max` 5. The default is `fast`. `max` also
  describes figures and tables with a model, which adds credits above two per
  page. <!-- B118 -->
- Text extraction (`extract_text`) costs 1 credit per 10 pages, rounded up,
  with a minimum of 1 credit. <!-- B146 -->
- One credit is USD 0.001. <!-- B134 -->

For any other operation the rate is on its page under
https://pdfluent.com/docs/api/reference/; do not guess it. Start with `fast`
and move to `auto` only when the text layer is missing or the tables come out
wrong.
