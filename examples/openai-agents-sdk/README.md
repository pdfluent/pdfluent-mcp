# OpenAI Agents SDK

Runs the `pdfluent-mcp` stdio server from the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/mcp/) with `MCPServerStdio`.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# No model, no API key: lists the tools and extracts one PDF
python main.py /absolute/path/to/report.pdf --offline

# An agent that answers questions about the PDF (needs OPENAI_API_KEY)
python main.py /absolute/path/to/report.pdf "Which pages mention retention?"
```

The server reads only inside `--root`. The example passes the PDF's folder as the root, so change that line if you want a wider scope. Tool paths must be absolute.

`pdfluent-mcp` is AGPL-3.0 or commercial, like the `pdfluent` package it runs on. See the main [README](../../README.md#licence).
