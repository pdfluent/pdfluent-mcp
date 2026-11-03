---
name: pdfluent
description: Read local PDF files as markdown, plain text, tables or structured blocks (headings, list items, tables with page and box), look up their metadata, search them, list and fill their form fields, and find the pages that need a vision model. Use when a task needs the contents of a PDF, citations to a page, table data from a PDF, or a form filled in.
---

# Reading and filling PDFs with PDFluent

The `pdfluent` MCP server (`pdfluent-mcp`) reads PDFs on this machine. Pass
it the file's absolute path; your documents stay on your machine, and it only touches
files inside its allowed roots. If a call answers "outside the allowed roots"
or "no allowed roots", tell the user which directory to allow; do not try
another spelling of the path.

## When to use which tool

- **Before reading a document you do not know**, call `get_metadata`: page
  count, title, whether it has form fields, whether it is encrypted, and
  `pages_needing_vision`.
- **To read, summarise or quote a document**, call `extract_markdown`.
  Headings, lists and tables keep their shape. For a long document, read it
  in windows with `pages` (a list of 0-based page numbers); the server
  refuses a call above its page limit and says so.
- **To find where something is mentioned**, call `search` first and read only
  the pages it names.
- **For table data as rows**, call `extract_tables`; each table has `rows`
  (lists of cell strings) and `header_rows`.
- **For the raw text layer** without reading-order repair, call
  `extract_text`.
- **To cite where something is, or to work with one kind of block**, call
  `extract_blocks`. Every block has `kind`, `text`, `page` (0-based) and
  `bbox`, in PDF points with the origin at the bottom left. Give page numbers
  to the user 1-based.
- **To fill a form**, call `list_form_fields`, map the user's answers onto the
  field names, then `fill_form` with those values and an `out_path` next to
  the original. The original is never changed. Report the `unknown` names
  back to the user.
- **Before you send a page to a vision model or ask for a screenshot**, read
  `pages_needing_vision` from `get_metadata` or `extract_blocks`, or call
  `vision_advice`. A page listed there has no text layer; it is usually a
  scan. Text extraction returns nothing for such a page, so do not report it
  as empty. Say it needs OCR or a vision model.

## Reading `confidence`

A block's `confidence` is the probability that the learned model gave for the
block's kind. `null` means no model decided it, so treat it as unknown, not as
low. When a decision depends on a block's kind and its confidence is low, check
the block's text before relying on the kind.

## Running heads

`extract_markdown` leaves out running heads and page numbers, and
`extract_blocks` does too unless you pass `include_furniture=true`. Ask for
them only when the task is about the headers or footers themselves.
