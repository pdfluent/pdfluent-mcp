# PDFluent PDF

This plugin connects Claude to the PDFluent PDF API through one remote MCP
server, `https://api.pdfluent.com/mcp/pdf`. It lists only the PDF tools: merge,
split, compress, redact, watermark, encrypt and fill PDFs, convert documents to
and from PDF, convert to PDF/A, run OCR and read barcodes. It also bundles a
skill that tells Claude which tool to pick and what a call costs.

Tools that read a PDF as markdown, tables or chunks are not on this server.
They live in the sibling plugin `pdfluent-extract`, which uses the same API key.

## What leaves your machine

The files Claude sends to a tool are uploaded to `api.pdfluent.com` and
processed there; the plugin runs no code on your computer and starts no local
server. The PDFluent API processes documents in the EU by default (as of 16
November 2026). <!-- B121 --> See the
[privacy policy](https://pdfluent.com/privacy/) for retention and regions.

## Setup

Install it from the marketplace in this repository:

```
claude plugin marketplace add pdfluent/pdfluent-mcp
claude plugin install pdfluent-pdf@pdfluent
```

1. Create an API key in the PDFluent console at https://pdfluent.com.
2. Enable the plugin. Claude Code asks for the key once and stores it as a
   sensitive setting; the key is sent as the `x-api-key` header and nowhere
   else. In a manual configuration use the placeholder `YOUR_API_KEY`.

Calls are paid from a prepaid credit balance. As of 22 November 2026, PDF
operations such as merge, split and compress cost 1 credit per 10 pages,
rounded up, with a minimum of 1 credit, and conversions cost 1 credit per
page. <!-- B119 -->

## Local alternative

To keep documents on your computer, use the separate local server in the
repository root, `pdfluent-mcp`, which reads files only inside the directories
you allow. It is not part of this plugin.

## Licence

MIT, see `LICENSE`. Source: https://github.com/pdfluent/pdfluent-mcp
