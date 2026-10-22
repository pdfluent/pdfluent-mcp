"""An MCP server over the PDFluent SDK.

Nine tools over a local PDF an agent names by path: the document as markdown,
as plain text, as blocks or as tables; its metadata; a text search; its form
fields, and a filled copy of it. It runs over stdio, one process per client,
with no network listener and no upload.

What it may touch is decided before any tool runs. A path is read or written
only inside an allowed root: the roots given with ``--root`` or
``PDFLUENT_MCP_ROOTS`` at start, plus the roots the client offers through the
MCP ``roots`` capability. Without any root the server answers every call with
the same sentence saying so, rather than reading whatever the agent names.

Three more limits keep one call from eating the session: a document above
``--max-bytes`` is refused; one call returns at most ``--max-pages`` pages, so
a long document is read in windows through ``pages`` (the engine still parses
the whole document for every window, because what a block is gets decided
against the rest of it: the page cap bounds the output, not the work); and a
result above ``--max-output-chars`` is cut and says so.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
import tempfile
import warnings
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, TypeVar, Union
from urllib.parse import unquote, urlparse

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ClientCapabilities, RootsCapability, ToolAnnotations

from pdfluent import Document, EmptyFileError, FileDataError, PdfluentEncryptedError, PdfluentError

# What the engine raises for bytes that are not a PDF: the PyMuPDF-compatible
# names, which are RuntimeErrors rather than PdfluentErrors.
ENGINE_ERRORS = (PdfluentError, FileDataError, EmptyFileError)

T = TypeVar("T")

ROOTS_ENV = "PDFLUENT_MCP_ROOTS"
MAX_PAGES_ENV = "PDFLUENT_MCP_MAX_PAGES"
MAX_BYTES_ENV = "PDFLUENT_MCP_MAX_BYTES"
MAX_OUTPUT_ENV = "PDFLUENT_MCP_MAX_OUTPUT_CHARS"
DEFAULT_MAX_PAGES = 200
DEFAULT_MAX_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_OUTPUT_CHARS = 200_000
MAX_QUERY_CHARS = 1000
SNIPPETS_PER_PAGE = 3
SNIPPET_RADIUS = 80
SEARCH_SNIPPET_PAGES = 20

INSTRUCTIONS = (
    "Read and fill local PDF files inside the allowed roots. Pass absolute paths. "
    "Use extract_markdown to read or quote a document, extract_text for the plain "
    "text layer, extract_tables for table data as rows, extract_blocks when you need "
    "the page and box of what you cite, get_metadata before reading a document you "
    "do not know, search to find the pages that mention something, and "
    "list_form_fields then fill_form to complete a form into a new file. Page "
    "numbers are 0-based in every argument and result. A page listed as needing "
    "vision has no text layer: nothing the text tools return for it is its content."
)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
# Destructive because `overwrite=true` replaces an existing file; without it the
# tool refuses to touch anything that exists.
WRITES_A_FILE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False)

# macOS and Windows filesystems fold case by default: two spellings, one file.
CASE_FOLDS = sys.platform in ("darwin", "win32")


@dataclass
class Limits:
    """What the server may touch, decided at start and never by a tool."""

    roots: List[str] = field(default_factory=list)
    max_pages: int = DEFAULT_MAX_PAGES
    max_bytes: int = DEFAULT_MAX_BYTES
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS

    @classmethod
    def from_env(cls) -> "Limits":
        roots = [r for r in os.environ.get(ROOTS_ENV, "").split(os.pathsep) if r]
        return cls(
            roots=[_canonical(r) for r in roots],
            max_pages=_positive(os.environ.get(MAX_PAGES_ENV), DEFAULT_MAX_PAGES, MAX_PAGES_ENV),
            max_bytes=_positive(os.environ.get(MAX_BYTES_ENV), DEFAULT_MAX_BYTES, MAX_BYTES_ENV),
            max_output_chars=_positive(os.environ.get(MAX_OUTPUT_ENV), DEFAULT_MAX_OUTPUT_CHARS, MAX_OUTPUT_ENV),
        )


def _positive(value: Optional[str], default: int, name: str) -> int:
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except ValueError:
        raise SystemExit(f"{name} must be a positive integer, not {value!r}")
    if number <= 0:
        raise SystemExit(f"{name} must be a positive integer, not {value!r}")
    return number


def _canonical(path: str) -> str:
    """One spelling per file, so a symlink or ``..`` cannot step out of a root."""
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


LIMITS = Limits.from_env()

server = MCPServer(name="pdfluent", instructions=INSTRUCTIONS)


# -- paths ---------------------------------------------------------------------


def _root_from_uri(uri: str) -> Optional[str]:
    """A client root as a local directory, or None when it is not a file URI."""
    parsed = urlparse(str(uri))
    if parsed.scheme != "file":
        return None
    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc != "localhost":
        # A URI with a host part is a network share on Windows: keep the UNC spelling.
        path = f"//{parsed.netloc}{path}"
    elif os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
        path = path[1:]
    return _canonical(path)


async def _roots(ctx: Optional[Context]) -> List[str]:
    """Every root this call may touch: the configured ones plus the client's."""
    roots = list(LIMITS.roots)
    if ctx is None:
        return roots
    try:
        offers_roots = ctx.session.check_client_capability(ClientCapabilities(roots=RootsCapability()))
    except Exception:  # a session with no negotiated capabilities yet
        offers_roots = False
    if not offers_roots:
        return roots
    try:
        # Roots are deprecated in protocol 2026-07-28 (SEP-2577) and still the
        # way Claude Code names its directories; the SDK warns on every call,
        # which would reach the client's log once per tool call.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            listed = await ctx.session.list_roots()
    except Exception:
        # The client said it has roots and then did not answer: the configured
        # roots still stand, the client's do not get guessed.
        return roots
    for root in listed.roots:
        local = _root_from_uri(root.uri)
        if local is not None and local not in roots:
            roots.append(local)
    return roots


def _inside(path: str, roots: Sequence[str]) -> bool:
    for root in roots:
        try:
            if os.path.commonpath([path, root]) == root:
                return True
        except ValueError:  # different drives on Windows
            continue
    return False


def _refuse_outside(what: str, spelled: str, real: str, roots: Sequence[str]) -> None:
    """Refuse ``real`` outside the roots, naming the path as the caller spelled it.

    The refusal does not list the roots: a caller that is probing learns
    nothing from a refusal beyond the fact of it, and the user who configured
    the roots knows them.
    """
    if not roots:
        raise ToolError(
            f"cannot {what} {spelled!r}: no allowed roots. Start the server with "
            f"--root <directory> or set {ROOTS_ENV}, or use a client that offers "
            "MCP roots; the server reads and writes nothing outside them."
        )
    if not _inside(real, roots):
        raise ToolError(f"cannot {what} {spelled!r}: it is outside the allowed roots")


def _absolute(path: str) -> str:
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        raise ToolError(f"{path!r} is relative; pass the absolute path of the file")
    return expanded


def _readable_path(path: str, roots: Sequence[str]) -> str:
    """``path`` as the file to open, or a `ToolError` naming what is wrong."""
    real = _canonical(_absolute(path))
    _refuse_outside("read", path, real, roots)
    if not os.path.isfile(real):
        raise ToolError(f"no file at {path!r}; pass the path of a local PDF")
    size = os.path.getsize(real)
    if size > LIMITS.max_bytes:
        raise ToolError(
            f"{path!r} is {size} bytes, above the limit of {LIMITS.max_bytes} bytes "
            f"per document ({MAX_BYTES_ENV} or --max-bytes raises it)"
        )
    return real


def _same_file(a: str, b: str) -> bool:
    """Whether two canonical paths name one file: by inode where both exist
    (hard links, case), by case-folded spelling on a case-folding filesystem."""
    try:
        if os.path.samefile(a, b):
            return True
    except OSError:
        pass
    if CASE_FOLDS:
        return os.path.normcase(a).casefold() == os.path.normcase(b).casefold()
    return a == b


def _refuse_target(path: str, target: str, source: str, overwrite: bool) -> None:
    """The checks on a write target, run before the engine writes and again
    after, so the window between them is as narrow as a rename."""
    if os.path.islink(target):
        raise ToolError(f"cannot write {path!r}: it is a symbolic link; the server never writes through one")
    if os.path.isdir(target):
        raise ToolError(f"cannot write {path!r}: it is a directory; pass a file path")
    if _same_file(target, source):
        raise ToolError(
            f"cannot write {path!r}: it is the input file. Pass a different out_path; "
            "the original is left as it was."
        )
    if os.path.lexists(target) and not overwrite:
        raise ToolError(f"cannot write {path!r}: it already exists; pass overwrite=true to replace it")


def _writable_path(path: str, roots: Sequence[str], source: str, overwrite: bool) -> str:
    """``path`` as the file to write, or a `ToolError` naming what is wrong.

    The target itself is never resolved through a link: the directory is
    canonicalised, the last component is kept as written, and a link there
    is refused rather than followed.
    """
    expanded = _absolute(path)
    parent = _canonical(os.path.dirname(expanded))
    target = os.path.join(parent, os.path.basename(expanded))
    _refuse_outside("write", path, target, roots)
    if not os.path.isdir(parent):
        raise ToolError(f"cannot write {path!r}: its directory does not exist")
    _refuse_target(path, target, source, overwrite)
    return target


def _write_atomically(path: str, target: str, source: str, overwrite: bool, save: Callable[[str], None]) -> None:
    """Save into a temp file beside ``target`` and rename it into place.

    A save that fails leaves nothing behind; the target is checked again
    after the save, so a file or link that appeared meanwhile is refused.
    """
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".pdfluent-mcp-", suffix=".tmp")
    os.close(fd)
    try:
        save(tmp)
        _refuse_target(path, target, source, overwrite)
        os.replace(tmp, target)
        # mkstemp creates 0600; a file the user asked for gets the usual mode.
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(target, 0o666 & ~umask)
    finally:
        if os.path.lexists(tmp):
            os.remove(tmp)


# -- documents -----------------------------------------------------------------


def _open(real: str) -> Document:
    return Document(real)


def _page_list(doc: Document, pages: Optional[List[int]], real: str) -> List[int]:
    """The 0-based pages one call reads, within the document and the cap."""
    count = doc.page_count
    if pages is None:
        if count > LIMITS.max_pages:
            raise ToolError(
                f"{real!r} has {count} pages, above the limit of {LIMITS.max_pages} "
                f"per call; pass pages (0-based) to read it in windows, or raise "
                f"{MAX_PAGES_ENV}"
            )
        return list(range(count))
    if not pages:
        raise ToolError("pages is empty; omit it for the whole document or list 0-based page numbers")
    wrong = [p for p in pages if not isinstance(p, int) or isinstance(p, bool) or p < 0 or p >= count]
    if wrong:
        raise ToolError(
            f"pages {wrong} are outside this document: it has {count} pages, numbered 0 to {count - 1}"
        )
    wanted = sorted(set(pages))
    if len(wanted) > LIMITS.max_pages:
        raise ToolError(
            f"{len(wanted)} pages asked for, above the limit of {LIMITS.max_pages} per call; "
            f"ask for fewer pages or raise {MAX_PAGES_ENV}"
        )
    return wanted


def _readable(tool: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """A PDFluent error as a message the agent reads.

    The server hides the text of an exception it did not expect, which is right
    for a bug and wrong for "this file is not a PDF": the agent can act on that,
    so it is raised as a `ToolError`, whose message reaches the client.
    """

    @functools.wraps(tool)
    async def wrapped(*args: Any, **kwargs: Any) -> T:
        try:
            return await tool(*args, **kwargs)
        except ENGINE_ERRORS as exc:
            raise ToolError(f"{type(exc).__name__}: {_without_paths(str(exc))}") from exc

    return wrapped


_ABSOLUTE_PATH = re.compile(r"(?<![\w:])(?:/[^\s'\"]+|[A-Za-z]:\\[^\s'\"]+)")


def _without_paths(message: str) -> str:
    """An engine message with every absolute path replaced by its last component."""
    return _ABSOLUTE_PATH.sub(lambda m: os.path.basename(m.group(0)) or "<path>", message)


def _cap_text(text: str) -> str:
    """``text`` within the output limit, with the cut stated at the end."""
    limit = LIMITS.max_output_chars
    if len(text) <= limit:
        return text
    return (
        text[:limit]
        + f"\n\n[truncated: {limit} of {len(text)} characters shown; the limit is "
        f"--max-output-chars ({MAX_OUTPUT_ENV}). Ask for fewer pages.]"
    )


def _cap_json(out: Dict[str, Any], key: str) -> Dict[str, Any]:
    """``out`` with the list under ``key`` shortened until the JSON fits.

    The cut is stated under ``truncated`` with how many entries were kept
    of how many there were, so the agent knows it has not seen everything.
    """
    limit = LIMITS.max_output_chars
    items = out[key]
    total = len(items)
    if len(json.dumps(out)) <= limit:
        return out
    kept = total
    while kept > 0 and len(json.dumps(out)) > limit:
        kept = max(0, min(kept - 1, int(kept * limit / max(1, len(json.dumps(out))))))
        out[key] = items[:kept]
        out["truncated"] = {"key": key, "kept": kept, "total": total, "limit": MAX_OUTPUT_ENV}
    return out


async def _in_thread(fn: Callable[..., T], *args: Any) -> T:
    """Run the engine off the event loop, so the session still answers pings."""
    return await anyio.to_thread.run_sync(fn, *args)


def _block(block: Any) -> Dict[str, Any]:
    """One block as the fields it carries, and none it does not."""
    out: Dict[str, Any] = {
        "kind": block.kind,
        "text": block.text,
        "page": block.page,
        "bbox": list(block.bbox),
        # Null where no model spoke about this block: unknown, not low.
        "confidence": block.confidence,
    }
    for name in ("level", "ordinal", "row", "column", "row_span", "column_span", "header"):
        value = getattr(block, name)
        if value is not None:
            out[name] = value
    if block.continues_previous:
        out["continues_previous"] = True
    return out


def _advice(advice: Any) -> Dict[str, Any]:
    return {
        "page": advice.page,
        "needs_vision": advice.needs_vision,
        "no_text_layer": advice.no_text_layer,
        "low_confidence_table": advice.low_confidence_table,
        "figure": advice.figure,
    }


def _tables(blocks: Sequence[Any]) -> List[Dict[str, Any]]:
    """Table cells, in reading order, as tables of rows.

    Cells arrive row by row; a cell at row 0, column 0 (or on another page)
    starts a new table. A spanning cell is placed at its first row and column
    and the covered cells stay empty, so every row has the table's width.
    """
    tables: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    cells: List[Any] = []

    def finish() -> None:
        if current is None or not cells:
            return
        height = max(c.row + (c.row_span or 1) for c in cells)
        width = max(c.column + (c.column_span or 1) for c in cells)
        rows = [["" for _ in range(width)] for _ in range(height)]
        header_rows = 0
        for c in cells:
            rows[c.row][c.column] = c.text
            if c.header:
                header_rows = max(header_rows, c.row + 1)
        current["rows"] = rows
        current["header_rows"] = header_rows
        tables.append(current)

    for b in blocks:
        if b.kind != "table_cell" or b.row is None or b.column is None:
            continue
        starts_new = (
            current is None
            or b.page != current["page"]
            or (b.row == 0 and b.column == 0)
        )
        if starts_new:
            finish()
            current = {"page": b.page}
            cells = []
        cells.append(b)
    finish()
    return tables


def _snippets(text: str, query: str) -> List[str]:
    """Up to SNIPPETS_PER_PAGE windows of ``text`` around ``query``, case-folded."""
    folded, needle = text.casefold(), query.casefold()
    out: List[str] = []
    start = 0
    while len(out) < SNIPPETS_PER_PAGE:
        at = folded.find(needle, start)
        if at < 0:
            break
        lo, hi = max(0, at - SNIPPET_RADIUS), min(len(text), at + len(needle) + SNIPPET_RADIUS)
        window = " ".join(text[lo:hi].split())
        out.append(("…" if lo > 0 else "") + window + ("…" if hi < len(text) else ""))
        start = at + len(needle)
    return out


def _metadata(real: str, spelled: str) -> Dict[str, Any]:
    """The document described, named as the caller spelled it."""
    # Opening defers the unlock, so a document that needs a password says so
    # at the first read, not in the constructor.
    try:
        doc = Document(real)
        info = doc.metadata
        fields = doc.get_form_fields()
        advice = doc.vision_advice()
    except PdfluentEncryptedError as exc:
        return {
            "path": spelled,
            "bytes": os.path.getsize(real),
            "encrypted": True,
            "needs_password": True,
            "detail": _without_paths(str(exc)),
        }
    out: Dict[str, Any] = {
        "path": spelled,
        "bytes": os.path.getsize(real),
        "pages": doc.page_count,
        "title": info.title,
        "author": info.author,
        "subject": info.subject,
        "created": info.creation_date,
        "modified": info.mod_date,
        "format": info.format,
        "encrypted": info.encryption is not None,
        "encryption": info.encryption,
        "has_forms": bool(fields),
        "form_fields": len(fields),
        "signatures": len(doc.signatures()),
        "bookmarks": len(doc.bookmarks),
        "pages_needing_vision": [a.page for a in advice if a.needs_vision],
    }
    return out


# -- tools ---------------------------------------------------------------------


@server.tool(annotations=READ_ONLY)
@_readable
async def extract_markdown(
    path: str,
    pages: Optional[List[int]] = None,
    quality: str = "fast",
    ctx: Context = None,  # type: ignore[assignment]
) -> str:
    """A local PDF as markdown, in reading order.

    Headings become ``#`` to ``###``, list items ``-`` and ``1.``, a table a pipe
    table (or HTML where markdown cannot hold its shape), and a change of page an
    HTML comment. Running heads and page numbers are left out.

    Args:
        path: The PDF's absolute path on this machine.
        pages: The 0-based pages to return; omit for the whole document, up to
            the server's page limit. The whole document is still read, because
            what a block is gets decided against the rest of it.
        quality: ``"fast"`` (default) or ``"balanced"``, the layout-model tier,
            which needs the models installed on this machine.
    """
    roots = await _roots(ctx)
    real = _readable_path(path, roots)

    def work() -> str:
        doc = _open(real)
        wanted = _page_list(doc, pages, real)
        return _cap_text(doc.extract_markdown(pages=wanted, quality=quality))

    return await _in_thread(work)


@server.tool(annotations=READ_ONLY)
@_readable
async def extract_text(
    path: str,
    pages: Optional[List[int]] = None,
    ctx: Context = None,  # type: ignore[assignment]
) -> str:
    """The plain text layer of a local PDF, page by page.

    Each page starts with ``<!-- page N -->`` (N 0-based). No reading-order
    repair and no structure: use extract_markdown for that. A page with no text
    layer (a scan) yields nothing here; get_metadata names those pages.

    Args:
        path: The PDF's absolute path on this machine.
        pages: The 0-based pages to return; omit for the whole document, up to
            the server's page limit.
    """
    roots = await _roots(ctx)
    real = _readable_path(path, roots)

    def work() -> str:
        doc = _open(real)
        parts = []
        for index in _page_list(doc, pages, real):
            parts.append(f"<!-- page {index} -->\n{doc[index].extract_text().strip()}")
        return _cap_text("\n\n".join(parts))

    return await _in_thread(work)


@server.tool(annotations=READ_ONLY)
@_readable
async def extract_tables(
    path: str,
    pages: Optional[List[int]] = None,
    ctx: Context = None,  # type: ignore[assignment]
) -> Dict[str, Any]:
    """The tables of a local PDF as rows of cell text.

    ``tables`` holds one entry per table in reading order: ``page`` (0-based),
    ``rows`` (a list of rows, each a list of cell strings, every row the table's
    width) and ``header_rows`` (how many leading rows are header rows). A
    spanning cell sits at its first row and column; the cells it covers are
    empty strings.

    Args:
        path: The PDF's absolute path on this machine.
        pages: The 0-based pages to look at; omit for the whole document, up to
            the server's page limit.
    """
    roots = await _roots(ctx)
    real = _readable_path(path, roots)

    def work() -> Dict[str, Any]:
        doc = _open(real)
        wanted = _page_list(doc, pages, real)
        return _cap_json({"tables": _tables(doc.extract_blocks(pages=wanted))}, "tables")

    return await _in_thread(work)


@server.tool(annotations=READ_ONLY)
@_readable
async def extract_blocks(
    path: str,
    pages: Optional[List[int]] = None,
    include_furniture: bool = False,
    ctx: Context = None,  # type: ignore[assignment]
) -> Dict[str, Any]:
    """A local PDF as blocks, in reading order, with where each one came from.

    Each block has ``kind`` (paragraph, heading, list_item, table_cell, header,
    footer), ``text``, ``page`` (0-based), ``bbox`` ([x0, y0, x1, y1] in PDF
    points, origin bottom-left) and ``confidence``: the probability of the
    learned model that decided the block's kind, or null where no model did --
    null means unknown, not low. Headings carry ``level``, list items ``level``
    and ``ordinal``, table cells ``row``, ``column``, ``row_span``,
    ``column_span`` and ``header``.

    ``pages_needing_vision`` lists the pages in the window whose text layer is
    missing: nothing this returns for them is the page's content.

    Args:
        path: The PDF's absolute path on this machine.
        pages: The 0-based pages to return; omit for the whole document, up to
            the server's page limit.
        include_furniture: Keep running heads and page numbers (kinds header and
            footer); they are left out by default because they repeat on every
            page and crowd out the content.
    """
    roots = await _roots(ctx)
    real = _readable_path(path, roots)

    def work() -> Dict[str, Any]:
        doc = _open(real)
        wanted = _page_list(doc, pages, real)
        blocks = [
            _block(b)
            for b in doc.extract_blocks(pages=wanted)
            if include_furniture or b.kind not in ("header", "footer")
        ]
        window = set(wanted)
        needing = [a.page for a in doc.vision_advice() if a.needs_vision and a.page in window]
        return _cap_json({"blocks": blocks, "pages_needing_vision": needing}, "blocks")

    return await _in_thread(work)


@server.tool(annotations=READ_ONLY)
@_readable
async def get_metadata(path: str, ctx: Context = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """What a local PDF is, before reading it.

    ``pages``, ``title``, ``author``, ``subject``, ``created``, ``modified``,
    ``format`` (the PDF version), ``encrypted`` with the ``encryption`` filter
    name, ``has_forms`` with the ``form_fields`` count, the number of
    ``signatures`` and ``bookmarks``, and ``pages_needing_vision``: the 0-based
    pages that draw ink but carry no text layer. A document that needs a
    password to open answers ``encrypted: true`` and ``needs_password: true``
    and nothing else.

    Args:
        path: The PDF's absolute path on this machine.
    """
    roots = await _roots(ctx)
    real = _readable_path(path, roots)
    return await _in_thread(_metadata, real, path)


@server.tool(annotations=READ_ONLY)
@_readable
async def search(path: str, query: str, ctx: Context = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """The pages of a local PDF that mention ``query``, with a snippet each.

    ``pages`` lists every matching 0-based page. ``snippets`` gives up to three
    windows of text around the match on each of the first twenty matching
    pages, so an agent can decide which pages to read in full with
    extract_markdown. Matching is case-insensitive on the text layer; a scanned
    page cannot match.

    Args:
        path: The PDF's absolute path on this machine.
        query: The text to look for, as written in the document.
    """
    if not query or not query.strip():
        raise ToolError("query is empty; pass the text to look for")
    if len(query) > MAX_QUERY_CHARS:
        raise ToolError(f"query is {len(query)} characters, above the limit of {MAX_QUERY_CHARS}")
    roots = await _roots(ctx)
    real = _readable_path(path, roots)

    def work() -> Dict[str, Any]:
        doc = _open(real)
        found = sorted(set(doc.search(query)))
        snippets = []
        for index in found[:SEARCH_SNIPPET_PAGES]:
            for text in _snippets(doc[index].extract_text(), query):
                snippets.append({"page": index, "text": text})
        return _cap_json({"query": query, "pages": found, "snippets": snippets}, "snippets")

    return await _in_thread(work)


@server.tool(annotations=READ_ONLY)
@_readable
async def list_form_fields(path: str, ctx: Context = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """The interactive form fields of a local PDF.

    ``fields`` holds one entry per field: ``name`` (the fully qualified name
    fill_form takes), ``type`` (text, button, choice, signature or unknown),
    ``value`` (the current value, or null) and ``page`` (0-based, or null when
    the field has no widget on a page). An empty list means the document has
    no AcroForm fields.

    Args:
        path: The PDF's absolute path on this machine.
    """
    roots = await _roots(ctx)
    real = _readable_path(path, roots)

    def work() -> Dict[str, Any]:
        fields = [
            {"name": f.name, "type": f.field_type, "value": f.value, "page": f.page}
            for f in _open(real).get_form_fields()
        ]
        return _cap_json({"fields": fields}, "fields")

    return await _in_thread(work)


@server.tool(annotations=WRITES_A_FILE)
@_readable
async def fill_form(
    path: str,
    values: Dict[str, Union[str, List[str]]],
    out_path: str,
    overwrite: bool = False,
    ctx: Context = None,  # type: ignore[assignment]
) -> Dict[str, Any]:
    """Fill the form fields of a local PDF and write the result to a new file.

    ``values`` maps a field name from list_form_fields to its new value: a
    string for a text field, a check box or a combo box, a list of strings for
    a multi-select list box. The input file is never changed; ``out_path`` must
    be a different path inside an allowed root, and one that does not exist
    yet unless ``overwrite`` is true. A symbolic link at ``out_path`` is
    refused either way. The result names the fields that were ``set`` and the
    names that were ``unknown``; nothing is written when no field was set.

    Args:
        path: The absolute path of the PDF to fill.
        values: Field name to new value.
        out_path: The absolute path to write the filled PDF to.
        overwrite: Replace a file that already exists at out_path.
    """
    if not values:
        raise ToolError("values is empty; pass at least one field name and value")
    roots = await _roots(ctx)
    real = _readable_path(path, roots)
    target = _writable_path(out_path, roots, real, overwrite)

    def work() -> Dict[str, Any]:
        doc = _open(real)
        known = {f.name for f in doc.get_form_fields()}
        done, unknown = [], []
        for name, value in values.items():
            if name not in known:
                unknown.append(name)
                continue
            if isinstance(value, list):
                ok = doc.set_multi_select(name, [str(v) for v in value])
            else:
                ok = doc.set_form_field(name, str(value))
            (done if ok else unknown).append(name)
        if not done:
            raise ToolError(
                f"none of the fields {unknown} exist in {path!r}; nothing was written. "
                f"The document's fields are {sorted(known)}"
            )
        _write_atomically(out_path, target, real, overwrite, doc.save)
        return {"written": target, "set": done, "unknown": unknown}

    return await _in_thread(work)


@server.tool(annotations=READ_ONLY)
@_readable
async def vision_advice(path: str, ctx: Context = None) -> Dict[str, Any]:  # type: ignore[assignment]
    """Which pages of a local PDF are worth sending to a vision model, and why.

    ``advice`` holds one entry per page. ``needs_vision`` is true when any reason holds. Today
    only ``no_text_layer`` is measured -- the page draws ink but yields no text,
    as a scan does; ``low_confidence_table`` and ``figure`` are always false
    until the engine can measure them.

    Args:
        path: The PDF's absolute path on this machine.
    """
    roots = await _roots(ctx)
    real = _readable_path(path, roots)
    return await _in_thread(lambda: _cap_json({"advice": [_advice(a) for a in _open(real).vision_advice()]}, "advice"))


# -- entry point ---------------------------------------------------------------


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pdfluent-mcp",
        description="MCP server over the PDFluent SDK, over stdio.",
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        metavar="DIR",
        help=f"a directory the server may read and write in; repeatable. Also {ROOTS_ENV} "
        f"({os.pathsep!r}-separated) and the client's MCP roots.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        metavar="N",
        help=f"pages one call may read (default {DEFAULT_MAX_PAGES}; also {MAX_PAGES_ENV})",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=None,
        metavar="N",
        help=f"largest document the server opens (default {DEFAULT_MAX_BYTES}; also {MAX_BYTES_ENV})",
    )
    parser.add_argument(
        "--max-output-chars",
        type=int,
        default=None,
        metavar="N",
        help=f"characters one tool result may hold before it is cut and says so "
        f"(default {DEFAULT_MAX_OUTPUT_CHARS}; also {MAX_OUTPUT_ENV})",
    )
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    return parser.parse_args(list(argv))


def configure(argv: Sequence[str]) -> Limits:
    """Apply the command line on top of the environment; returns the limits."""
    args = _parse(argv)
    if args.version:
        from pdfluent_mcp import __version__

        print(f"pdfluent-mcp {__version__}")
        raise SystemExit(0)
    for root in args.root:
        real = _canonical(root)
        if not os.path.isdir(real):
            raise SystemExit(f"--root {root!r} is not a directory")
        if real not in LIMITS.roots:
            LIMITS.roots.append(real)
    if args.max_pages is not None:
        LIMITS.max_pages = _positive(str(args.max_pages), DEFAULT_MAX_PAGES, "--max-pages")
    if args.max_bytes is not None:
        LIMITS.max_bytes = _positive(str(args.max_bytes), DEFAULT_MAX_BYTES, "--max-bytes")
    if args.max_output_chars is not None:
        LIMITS.max_output_chars = _positive(str(args.max_output_chars), DEFAULT_MAX_OUTPUT_CHARS, "--max-output-chars")
    return LIMITS


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Run the server over stdio, which is how every MCP client starts it."""
    configure(sys.argv[1:] if argv is None else argv)
    if not LIMITS.roots:
        # Not fatal: a client may offer roots after the handshake. Said once,
        # on stderr, where a client's log shows it.
        print(
            f"pdfluent-mcp: no --root and no {ROOTS_ENV}; only the client's MCP roots "
            "will be readable",
            file=sys.stderr,
        )
    server.run("stdio")


if __name__ == "__main__":
    main()
