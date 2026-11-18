# Copyright (c) 2026 Innovation Trigger B.V.
#
# PDFluent MCP server over stdio, as a container.
#
#   docker build -t pdfluent-mcp .
#   docker run -i --rm -v "$PWD:/data" pdfluent-mcp
#
# Documents are read from /data, so mount the folder you want the server to
# see there. Nothing is uploaded; the server only talks over stdin and stdout.
FROM python:3.12-slim

ARG PDFLUENT_VERSION=1.4.0

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE LICENSE-COMMERCIAL ./
COPY pdfluent_mcp ./pdfluent_mcp
RUN pip install "pdfluent==${PDFLUENT_VERSION}" . \
    && useradd --create-home --uid 10001 mcp \
    && mkdir /data && chown mcp /data

USER mcp
WORKDIR /data

LABEL org.opencontainers.image.title="pdfluent-mcp" \
      org.opencontainers.image.source="https://github.com/pdfluent/pdfluent-mcp" \
      org.opencontainers.image.licenses="AGPL-3.0-only OR LicenseRef-PDFluent-Commercial"

ENTRYPOINT ["pdfluent-mcp", "--root", "/data"]
