---
name: pdfluent-hosted
description: Use the PDFluent hosted API tools to turn PDFs into markdown, text or tables, to run PDF operations (merge, split, compress, redact, watermark, fill forms, convert) and to check what a call costs in credits. Use when a task needs the content of a PDF sent to the hosted service, a PDF operation the local pdfluent tools do not offer, or when the user asks what a PDF call will cost.
---

# PDFluent hosted API

The `pdfluent-hosted` MCP server calls the PDFluent hosted API at
`https://api.pdfluent.com/mcp`. Each API operation is one tool. The tool name
is the operation id with dots turned into underscores, for example
`extract_markdown`, `extract_tables`, `pdf_merge`. Files go in as base64 in
`files`; the operation's options go in `options`. The full tool list is at
https://pdfluent.com/docs/api/mcp/.

The documents you send leave this machine. If the user wants a document to stay
local, use the local `pdfluent` MCP server (`pdfluent-mcp`) instead, and say so
before sending anything.

## Setup

The plugin reads the API key from the `PDFLUENT_API_KEY` environment variable.
If a call answers 401, the key is missing or invalid: tell the user to create a
key in the PDFluent console and export `PDFLUENT_API_KEY` before starting
Claude Code. Do not ask the user to paste the key into the chat.

## Which tool

- **Read or quote a PDF**: `extract_markdown`. Headings, lists and tables keep
  their shape. Pass `options.pages` (1-based) to read a window of a long
  document.
- **Table data as rows**: `extract_tables`.
- **Plain text layer**: `extract_text`.
- **Find where something is mentioned**: `search`, then read only those pages.
- **Know what a file is before spending credits**: `info` (page count, whether
  it is encrypted) first, then pick the quality.
- **Change a PDF**: `pdf_merge`, `pdf_split`, `pdf_pages`, `pdf_compress`,
  `pdf_redact`, `pdf_watermark`, `pdf_flatten`, `pdf_encrypt`,
  `pdf_decrypt`, `pdf_metadata`, `pdf_replace_text`. These write a new file;
  they are not read-only.
- **Fill a form**: `forms_fields` to list the fields, then `forms_fill`.
- **Convert**: `convert_office`, `convert_html`, `convert_url`,
  `convert_to_images`, `convert_to_xlsx`, `convert_to_pptx`, `pdfa_convert`.
- **Scanned pages**: `ocr_searchable`, or `extract_markdown` with
  `options.quality` set to `auto`.

Tools that only read declare `readOnlyHint: true`. Ask the user before calling
a tool that changes a document or spends a large number of credits.

## Cost in credits

Calls are paid from a prepaid credit balance. Every response carries
`x-pdfluent-pages` and `x-pdfluent-credits`; report them back after a call.

- Extraction costs credits per page by quality: `fast` 1, `balanced` 2,
  `auto` 3, `max` 5. The default is `fast`. `max` also describes figures and
  tables with a model, which adds credits above two per page. <!-- B118 -->
- PDF operations such as merge, split, compress, pages, encrypt, decrypt,
  watermark, redact, replace text, flatten and metadata cost 1 credit per 10
  pages, rounded up to whole blocks of 10 pages, with a minimum of 1 credit.
  Conversions cost 1 credit per page. <!-- B119 -->
- Searchable OCR costs 3 credits per page. <!-- B146 -->
- Extract and the PDF operations share one balance. <!-- B123 -->
- One credit is USD 0.001. <!-- B134 -->

For any other operation the rate is on its page under
https://pdfluent.com/docs/api/reference/; do not guess it. Start with `fast`
and move to `auto` only when the text layer is missing or the tables come out
wrong.
