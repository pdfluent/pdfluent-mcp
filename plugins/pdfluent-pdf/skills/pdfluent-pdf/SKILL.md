---
name: pdfluent-pdf
description: Use the PDFluent PDF API tools to run PDF operations (merge, split, compress, redact, watermark, encrypt, fill forms, convert, PDF/A, OCR, barcodes) and to check what a call costs in credits. Use when a task needs to change or convert a PDF with the hosted service, or when the user asks what a PDF call will cost.
---

# PDFluent PDF API

The `pdfluent-pdf` MCP server calls the PDFluent PDF API at
`https://api.pdfluent.com/mcp/pdf`. Each API operation is one tool. The tool
name is the operation id with dots turned into underscores, for example
`pdf_merge` or `forms_fill`. Files go in as base64 in `files`; the operation's
options go in `options`. The full tool list is at
https://pdfluent.com/docs/api/mcp/.

This server holds the PDF tools only. To read a PDF as markdown, tables or
chunks, use the `pdfluent-extract` plugin.

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

- **Know what a file is before spending credits**: `info` (page count, whether
  it is encrypted).
- **Change a PDF**: `pdf_merge`, `pdf_split`, `pdf_pages`, `pdf_compress`,
  `pdf_redact`, `pdf_watermark`, `pdf_flatten`, `pdf_encrypt`,
  `pdf_decrypt`, `pdf_metadata`, `pdf_page_boxes`, `pdf_replace_text`. These
  write a new file; they are not read-only.
- **Fill a form**: `forms_fields` to list the fields, then `forms_fill`.
  `forms_export` and `forms_import` move field data in and out;
  `forms_xfa_flatten` flattens an XFA form.
- **Convert**: `convert_office`, `convert_html`, `convert_url`,
  `convert_email`, `convert_template`, `convert_to_images`, `convert_to_xlsx`,
  `convert_to_pptx`.
- **Archive and accessibility**: `pdfa_validate`, `pdfa_convert`,
  `pdfua_check`.
- **E-invoices**: `zugferd_create`.
- **Scanned pages**: `ocr_searchable`.
- **Barcodes and signatures**: `barcodes_read`, `signatures_verify`.

Ask the user before calling a tool that changes a document or spends a large
number of credits.

## Cost in credits

Calls are paid from a prepaid credit balance. Every response carries
`x-pdfluent-pages` and `x-pdfluent-credits`; report them back after a call.

- PDF operations such as merge, split, compress, pages, encrypt, decrypt,
  watermark, redact, replace text, flatten and metadata cost 1 credit per 10
  pages, rounded up to whole blocks of 10 pages, with a minimum of 1 credit,
  as of 22 November 2026. Conversions cost 1 credit per page. <!-- B119 -->
- Searchable OCR costs 3 credits per page. Form operations cost 1 credit per
  10 pages. <!-- B146 -->
- One credit is USD 0.001. <!-- B134 -->

For any other operation the rate is on its page under
https://pdfluent.com/docs/api/reference/; do not guess it.
