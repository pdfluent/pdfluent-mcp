# PDFluent (hosted)

This plugin connects Claude to the PDFluent hosted API through one remote MCP
server, `https://api.pdfluent.com/mcp`. It gives Claude tools to read a PDF as
markdown, plain text or tables, to search it, to merge, split, compress, redact,
watermark and fill PDFs, and to convert documents. It also bundles a skill that
tells Claude which tool to pick and what a call costs.

## What leaves your machine

The files Claude sends to a tool are uploaded to `api.pdfluent.com` and
processed there; the plugin runs no code on your computer and starts no local
server. Processing happens in the EU by default. See the
[privacy policy](https://pdfluent.com/privacy/) for retention and regions.

## Setup

Install it from the marketplace in this repository:

```
/plugin install pdfluent-hosted --marketplace pdfluent/pdfluent-mcp
```

1. Create an API key in the PDFluent console at https://pdfluent.com.
2. Enable the plugin. Claude Code asks for the key once and stores it as a
   sensitive setting; the key is sent as the `x-api-key` header and nowhere
   else. In a manual configuration use the placeholder `YOUR_API_KEY`.

Calls are paid from a prepaid credit balance. Extraction costs 1 to 5 credits
per page depending on the quality you choose.

## Local alternative

To keep documents on your computer, use the separate local server in the
repository root, `pdfluent-mcp`, which reads files only inside the directories
you allow. It is not part of this plugin.

## Licence

MIT, see `LICENSE`. Source: https://github.com/pdfluent/pdfluent-mcp
