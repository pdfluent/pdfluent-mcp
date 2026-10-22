"""The MCP server over stdio, called the way every MCP client calls it.

A real client starts the server as a subprocess and speaks the protocol to it:
the tools are listed, then every tool is called on fixtures from this
repository -- fixtures/structured.pdf (a heading and a bulleted list on page
0, a ruled table on page 1, pinned by
crates/pdf-engine/tests/the_api_over_the_block_model.rs), fixtures/acroform.pdf
(text fields), fixtures/multi-page.pdf, fixtures/encrypted-user-secret.pdf and
one scanned page -- and the output is checked.

The second half is the fence: a path outside the allowed roots, however it is
spelled, is refused with a message that says so, and a server with no roots
at all reads nothing.
"""

import json
import os
import sys

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import ListRootsResult, Root

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
STRUCTURED_PDF = os.path.join(FIXTURES, "structured.pdf")
ACROFORM_PDF = os.path.join(FIXTURES, "acroform.pdf")
MULTI_PAGE_PDF = os.path.join(FIXTURES, "multi-page.pdf")
ENCRYPTED_PDF = os.path.join(FIXTURES, "encrypted-user-secret.pdf")
SCANNED_PDF = os.path.join(FIXTURES, "scan_01_sample.pdf")

ALL_TOOLS = [
    "extract_blocks",
    "extract_markdown",
    "extract_tables",
    "extract_text",
    "fill_form",
    "get_metadata",
    "list_form_fields",
    "search",
    "vision_advice",
]


def _session(body, args=(), env=None, client_roots=None):
    """Run ``body(session)`` against a freshly started server.

    ``args`` go on the server's command line (``--root`` and the limits);
    ``env`` replaces the roots variable; ``client_roots`` makes the client
    offer those directories through the MCP roots capability.
    """

    async def run():
        environment = {k: v for k, v in os.environ.items() if not k.startswith("PDFLUENT_MCP_")}
        if env:
            environment.update(env)
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "pdfluent_mcp.server", *args],
            env=environment,
        )
        callback = None
        if client_roots is not None:

            async def callback(_context):
                return ListRootsResult(roots=[Root(uri=f"file://{r}") for r in client_roots])

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, list_roots_callback=callback) as session:
                await session.initialize()
                return await body(session)

    return anyio.run(run)


def _call(tool, arguments, **kwargs):
    async def body(session):
        return await session.call_tool(tool, arguments)

    return _session(body, **kwargs)


def _payload(result):
    """A tool result as the value the tool returned."""
    assert not result.is_error, result.content
    if result.structured_content is not None:
        content = result.structured_content
        # A tool that returns a list or a string is wrapped as {"result": ...}.
        return content.get("result", content) if set(content) == {"result"} else content
    return json.loads(result.content[0].text)


def _error(result):
    assert result.is_error, result.content
    return result.content[0].text


ROOT = ("--root", FIXTURES)


# -- every tool, on a real document --------------------------------------------


def test_the_server_lists_every_tool():
    async def body(session):
        return await session.list_tools()

    tools = _session(body, args=ROOT).tools
    assert sorted(t.name for t in tools) == ALL_TOOLS
    hints = {t.name: t.annotations for t in tools}
    assert all(hints[n].read_only_hint for n in ALL_TOOLS if n != "fill_form")
    assert hints["fill_form"].read_only_hint is False


def test_extract_markdown_reads_a_heading_a_list_item_and_a_table():
    result = _call("extract_markdown", {"path": STRUCTURED_PDF}, args=ROOT)
    assert not result.is_error, result.content
    markdown = result.content[0].text
    assert "# Safety rules" in markdown
    assert "- Wear the issued boots on the floor." in markdown
    assert "| Band | Units | Rate |" in markdown


def test_extract_markdown_with_pages_returns_only_those_pages():
    result = _call("extract_markdown", {"path": STRUCTURED_PDF, "pages": [1]}, args=ROOT)
    markdown = result.content[0].text
    assert "| Band | Units | Rate |" in markdown
    assert "Safety rules" not in markdown


def test_extract_markdown_names_an_unknown_quality():
    text = _error(_call("extract_markdown", {"path": STRUCTURED_PDF, "quality": "best"}, args=ROOT))
    assert "best" in text


def test_extract_text_returns_the_text_layer_page_by_page():
    result = _call("extract_text", {"path": STRUCTURED_PDF}, args=ROOT)
    assert not result.is_error, result.content
    text = result.content[0].text
    assert text.startswith("<!-- page 0 -->")
    assert "<!-- page 1 -->" in text
    assert "Safety rules" in text
    assert "Band" in text

    only_second = _call("extract_text", {"path": STRUCTURED_PDF, "pages": [1]}, args=ROOT)
    assert "<!-- page 0 -->" not in only_second.content[0].text
    assert "Band" in only_second.content[0].text


def test_extract_tables_returns_the_table_as_rows():
    out = _payload(_call("extract_tables", {"path": STRUCTURED_PDF}, args=ROOT))
    (table,) = out["tables"]
    assert table["page"] == 1
    assert table["rows"][0] == ["Band", "Units", "Rate"]
    assert table["header_rows"] == 1
    assert len(table["rows"]) > 1
    assert all(len(row) == 3 for row in table["rows"])

    none = _payload(_call("extract_tables", {"path": STRUCTURED_PDF, "pages": [0]}, args=ROOT))
    assert none["tables"] == []


def test_extract_blocks_carries_kind_page_box_and_confidence():
    out = _payload(_call("extract_blocks", {"path": STRUCTURED_PDF}, args=ROOT))
    blocks = out["blocks"]
    heading = next(b for b in blocks if b["kind"] == "heading")
    assert heading["text"] == "Safety rules"
    assert heading["level"] == 1
    assert heading["page"] == 0
    assert len(heading["bbox"]) == 4
    # Present on every block, null where no model decided the kind.
    assert all("confidence" in b for b in blocks)
    cell = next(b for b in blocks if b["kind"] == "table_cell" and b["text"] == "Band")
    assert (cell["row"], cell["column"], cell["header"]) == (0, 0, True)
    assert out["pages_needing_vision"] == []


def test_get_metadata_describes_the_document():
    out = _payload(_call("get_metadata", {"path": ACROFORM_PDF}, args=ROOT))
    assert out["pages"] >= 1
    assert out["has_forms"] is True
    assert out["form_fields"] > 0
    assert out["encrypted"] is False
    assert out["bytes"] == os.path.getsize(ACROFORM_PDF)

    plain = _payload(_call("get_metadata", {"path": STRUCTURED_PDF}, args=ROOT))
    assert plain["has_forms"] is False
    assert plain["pages"] == 2
    assert plain["pages_needing_vision"] == []


def test_get_metadata_says_when_a_document_needs_a_password():
    out = _payload(_call("get_metadata", {"path": ENCRYPTED_PDF}, args=ROOT))
    assert out["encrypted"] is True
    assert out["needs_password"] is True
    assert "pages" not in out


def test_search_finds_the_page_and_quotes_a_snippet():
    out = _payload(_call("search", {"path": STRUCTURED_PDF, "query": "issued boots"}, args=ROOT))
    assert out["pages"] == [0]
    assert out["snippets"]
    assert out["snippets"][0]["page"] == 0
    assert "issued boots" in out["snippets"][0]["text"].lower()

    nothing = _payload(_call("search", {"path": STRUCTURED_PDF, "query": "xyzzy-not-here"}, args=ROOT))
    assert nothing == {"query": "xyzzy-not-here", "pages": [], "snippets": []}

    assert "empty" in _error(_call("search", {"path": STRUCTURED_PDF, "query": "  "}, args=ROOT))


def test_list_form_fields_names_every_field():
    out = _payload(_call("list_form_fields", {"path": ACROFORM_PDF}, args=ROOT))
    fields = out["fields"]
    assert fields
    assert all(set(f) == {"name", "type", "value", "page"} for f in fields)
    assert any(f["type"] == "text" for f in fields)

    none = _payload(_call("list_form_fields", {"path": STRUCTURED_PDF}, args=ROOT))
    assert none == {"fields": []}


def test_fill_form_writes_a_filled_copy_and_names_unknown_fields(tmp_path):
    fields = _payload(_call("list_form_fields", {"path": ACROFORM_PDF}, args=ROOT))["fields"]
    name = next(f["name"] for f in fields if f["type"] == "text")
    out_path = str(tmp_path / "filled.pdf")
    args = (*ROOT, "--root", str(tmp_path))

    out = _payload(
        _call(
            "fill_form",
            {"path": ACROFORM_PDF, "values": {name: "Jane Doe", "no_such_field": "x"}, "out_path": out_path},
            args=args,
        )
    )
    assert out["set"] == [name]
    assert out["unknown"] == ["no_such_field"]
    assert os.path.realpath(out["written"]) == os.path.realpath(out_path)

    filled = _payload(_call("list_form_fields", {"path": out_path}, args=args))["fields"]
    assert next(f["value"] for f in filled if f["name"] == name) == "Jane Doe"
    # The input is untouched.
    original = _payload(_call("list_form_fields", {"path": ACROFORM_PDF}, args=ROOT))["fields"]
    assert next(f["value"] for f in original if f["name"] == name) != "Jane Doe"


def test_fill_form_writes_nothing_when_no_field_matches(tmp_path):
    out_path = str(tmp_path / "filled.pdf")
    text = _error(
        _call(
            "fill_form",
            {"path": ACROFORM_PDF, "values": {"nope": "x"}, "out_path": out_path},
            args=(*ROOT, "--root", str(tmp_path)),
        )
    )
    assert "nothing was written" in text
    assert not os.path.exists(out_path)


def test_a_scanned_page_is_named_as_needing_vision():
    async def body(session):
        advice = await session.call_tool("vision_advice", {"path": SCANNED_PDF})
        blocks = await session.call_tool("extract_blocks", {"path": SCANNED_PDF})
        meta = await session.call_tool("get_metadata", {"path": SCANNED_PDF})
        return advice, blocks, meta

    advice, blocks, meta = _session(body, args=ROOT)
    (page,) = _payload(advice)["advice"]
    assert page["needs_vision"] is True
    assert page["no_text_layer"] is True
    assert _payload(blocks)["pages_needing_vision"] == [0]
    assert _payload(meta)["pages_needing_vision"] == [0]


# -- errors that name their cause ----------------------------------------------


def test_a_missing_file_is_an_error_the_agent_can_read():
    text = _error(_call("extract_markdown", {"path": os.path.join(FIXTURES, "no-such.pdf")}, args=ROOT))
    assert "no file at" in text


def test_a_file_that_is_not_a_pdf_is_an_error_the_agent_can_read(tmp_path):
    bogus = tmp_path / "notes.pdf"
    bogus.write_text("this is not a PDF")
    text = _error(_call("extract_blocks", {"path": str(bogus)}, args=("--root", str(tmp_path))))
    assert "FileDataError" in text


def test_pages_outside_the_document_are_named():
    text = _error(_call("extract_text", {"path": STRUCTURED_PDF, "pages": [0, 7]}, args=ROOT))
    assert "[7]" in text and "2 pages" in text
    assert "empty" in _error(_call("extract_text", {"path": STRUCTURED_PDF, "pages": []}, args=ROOT))


def test_the_page_limit_asks_for_windows():
    args = (*ROOT, "--max-pages", "1")
    text = _error(_call("extract_text", {"path": STRUCTURED_PDF}, args=args))
    assert "2 pages" in text and "limit of 1" in text and "pages" in text
    text = _error(_call("extract_text", {"path": STRUCTURED_PDF, "pages": [0, 1]}, args=args))
    assert "limit of 1" in text
    # Within the limit, the window is read.
    result = _call("extract_text", {"path": STRUCTURED_PDF, "pages": [1]}, args=args)
    assert "Band" in result.content[0].text
    # And the environment sets the same limit.
    text = _error(_call("extract_text", {"path": STRUCTURED_PDF}, args=ROOT, env={"PDFLUENT_MCP_MAX_PAGES": "1"}))
    assert "limit of 1" in text


def test_the_size_limit_refuses_a_large_document():
    size = os.path.getsize(MULTI_PAGE_PDF)
    text = _error(_call("get_metadata", {"path": MULTI_PAGE_PDF}, args=(*ROOT, "--max-bytes", str(size - 1))))
    assert f"{size} bytes" in text and f"limit of {size - 1}" in text
    text = _error(_call("get_metadata", {"path": MULTI_PAGE_PDF}, args=ROOT, env={"PDFLUENT_MCP_MAX_BYTES": "10"}))
    assert "limit of 10" in text


# -- the fence: allowed roots --------------------------------------------------


def test_a_server_without_roots_reads_nothing():
    text = _error(_call("extract_markdown", {"path": STRUCTURED_PDF}))
    assert "no allowed roots" in text
    assert "--root" in text and "PDFLUENT_MCP_ROOTS" in text


def test_a_path_outside_the_roots_is_refused(tmp_path):
    text = _error(_call("extract_markdown", {"path": STRUCTURED_PDF}, args=("--root", str(tmp_path))))
    assert "outside the allowed roots" in text
    # The refusal does not say which roots there are.
    assert os.path.realpath(str(tmp_path)) not in text


def test_dot_dot_cannot_step_out_of_a_root(tmp_path):
    inside = tmp_path / "inside"
    inside.mkdir()
    sneaky = os.path.join(str(inside), "..", "..", os.path.relpath(STRUCTURED_PDF, os.path.dirname(str(tmp_path))))
    text = _error(_call("extract_markdown", {"path": sneaky}, args=("--root", str(inside))))
    assert "outside the allowed roots" in text


def test_a_symlink_inside_a_root_cannot_point_outside(tmp_path):
    link = tmp_path / "link.pdf"
    os.symlink(STRUCTURED_PDF, str(link))
    text = _error(_call("extract_markdown", {"path": str(link)}, args=("--root", str(tmp_path))))
    assert "outside the allowed roots" in text


def test_a_root_prefix_is_not_a_root(tmp_path):
    # A root allows a file inside it and not a file in a sibling whose name only starts the same.
    root = tmp_path / "root"
    root.mkdir()
    sibling = tmp_path / "root-other"
    sibling.mkdir()
    pdf = sibling / "a.pdf"
    pdf.write_bytes(open(STRUCTURED_PDF, "rb").read())
    text = _error(_call("extract_markdown", {"path": str(pdf)}, args=("--root", str(root))))
    assert "outside the allowed roots" in text


def test_a_relative_path_is_refused():
    text = _error(_call("extract_markdown", {"path": "structured.pdf"}, args=ROOT))
    assert "relative" in text


def test_fill_form_cannot_write_outside_the_roots(tmp_path):
    outside = tmp_path / "escaped.pdf"
    text = _error(
        _call("fill_form", {"path": ACROFORM_PDF, "values": {"a": "b"}, "out_path": str(outside)}, args=ROOT)
    )
    assert "cannot write" in text and "outside the allowed roots" in text
    assert not outside.exists()


def test_fill_form_cannot_overwrite_its_input(tmp_path):
    copy = tmp_path / "form.pdf"
    copy.write_bytes(open(ACROFORM_PDF, "rb").read())
    before = copy.read_bytes()
    text = _error(
        _call("fill_form", {"path": str(copy), "values": {"a": "b"}, "out_path": str(copy)}, args=("--root", str(tmp_path)))
    )
    assert "it is the input file" in text
    assert copy.read_bytes() == before


def test_roots_come_from_the_environment_too():
    result = _call("extract_markdown", {"path": STRUCTURED_PDF}, env={"PDFLUENT_MCP_ROOTS": FIXTURES})
    assert "# Safety rules" in result.content[0].text


def test_roots_the_client_offers_are_allowed():
    without = _call("extract_markdown", {"path": STRUCTURED_PDF})
    assert without.is_error
    offered = _call("extract_markdown", {"path": STRUCTURED_PDF}, client_roots=[FIXTURES])
    assert not offered.is_error, offered.content
    assert "# Safety rules" in offered.content[0].text


def test_a_client_root_elsewhere_does_not_open_the_fixtures(tmp_path):
    text = _error(_call("extract_markdown", {"path": STRUCTURED_PDF}, client_roots=[str(tmp_path)]))
    assert "outside the allowed roots" in text


def test_a_root_that_is_not_a_directory_stops_the_server():
    with pytest.raises(Exception):
        _call("get_metadata", {"path": STRUCTURED_PDF}, args=("--root", os.path.join(FIXTURES, "nope")))


# -- writing: never over something that exists, never through a link -----------


def _case_insensitive(directory):
    probe = os.path.join(directory, "CaseProbe")
    open(probe, "w").close()
    return os.path.exists(os.path.join(directory, "caseprobe"))


def _text_field(path, args):
    fields = _payload(_call("list_form_fields", {"path": path}, args=args))["fields"]
    return next(f["name"] for f in fields if f["type"] == "text")


def test_fill_form_cannot_overwrite_its_input_under_another_spelling(tmp_path):
    if not _case_insensitive(str(tmp_path)):
        print("SKIPPED (not a pass): this filesystem is case-sensitive", file=sys.stderr)
        pytest.skip("case-sensitive filesystem")
    copy = tmp_path / "form.pdf"
    copy.write_bytes(open(ACROFORM_PDF, "rb").read())
    before = copy.read_bytes()
    args = ("--root", str(tmp_path))
    name = _text_field(str(copy), args)
    text = _error(
        _call("fill_form", {"path": str(copy), "values": {name: "x"}, "out_path": str(tmp_path / "FORM.PDF")}, args=args)
    )
    assert "it is the input file" in text
    assert copy.read_bytes() == before


def test_fill_form_refuses_an_existing_target_unless_asked(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("keep me")
    args = (*ROOT, "--root", str(tmp_path))
    name = _text_field(ACROFORM_PDF, args)
    text = _error(_call("fill_form", {"path": ACROFORM_PDF, "values": {name: "x"}, "out_path": str(target)}, args=args))
    assert "already exists" in text and "overwrite" in text
    assert target.read_text() == "keep me"
    out = _payload(
        _call(
            "fill_form",
            {"path": ACROFORM_PDF, "values": {name: "x"}, "out_path": str(target), "overwrite": True},
            args=args,
        )
    )
    assert out["written"] == str(target)
    assert target.read_bytes()[:4] == b"%PDF"
    assert not [p for p in os.listdir(str(tmp_path)) if p.startswith(".pdfluent-mcp-")]


def test_fill_form_never_writes_through_a_symlink(tmp_path):
    victim = tmp_path / "victim.pdf"
    victim.write_text("keep me")
    link = tmp_path / "link.pdf"
    os.symlink(str(victim), str(link))
    args = (*ROOT, "--root", str(tmp_path))
    name = _text_field(ACROFORM_PDF, args)
    for overwrite in (False, True):
        text = _error(
            _call(
                "fill_form",
                {"path": ACROFORM_PDF, "values": {name: "x"}, "out_path": str(link), "overwrite": overwrite},
                args=args,
            )
        )
        assert "symbolic link" in text
    assert victim.read_text() == "keep me"
    assert os.path.islink(str(link))


# -- output size -----------------------------------------------------------------


def test_text_output_is_capped_and_says_so():
    args = (*ROOT, "--max-output-chars", "200")
    text = _call("extract_markdown", {"path": STRUCTURED_PDF}, args=args).content[0].text
    assert "[truncated:" in text and "characters" in text
    assert len(text) < 400
    text = _call("extract_text", {"path": STRUCTURED_PDF}, args=ROOT, env={"PDFLUENT_MCP_MAX_OUTPUT_CHARS": "200"}).content[0].text
    assert "[truncated:" in text


def test_json_output_is_capped_and_says_so():
    args = (*ROOT, "--max-output-chars", "600")
    out = _payload(_call("extract_blocks", {"path": STRUCTURED_PDF}, args=args))
    assert out["truncated"]["kept"] < out["truncated"]["total"]
    assert len(json.dumps(out)) <= 900
    full = _payload(_call("extract_blocks", {"path": STRUCTURED_PDF}, args=ROOT))
    assert "truncated" not in full
    assert len(full["blocks"]) == out["truncated"]["total"]


def test_a_long_query_is_refused():
    text = _error(_call("search", {"path": STRUCTURED_PDF, "query": "x" * 1001}, args=ROOT))
    assert "query" in text and "1000" in text


def test_refusals_do_not_list_the_roots_and_keep_the_callers_spelling(tmp_path):
    spelled = os.path.join(str(tmp_path), "..", os.path.basename(str(tmp_path)), "x.pdf")
    text = _error(_call("get_metadata", {"path": spelled}, args=ROOT))
    assert spelled in text
    assert FIXTURES not in text


def test_get_metadata_keeps_the_callers_spelling_and_names_no_path_in_detail():
    spelled = os.path.join(FIXTURES, ".", "encrypted-user-secret.pdf")
    out = _payload(_call("get_metadata", {"path": spelled}, args=ROOT))
    assert out["path"] == spelled
    assert out["needs_password"] is True
    assert FIXTURES not in out["detail"]
    plain = _payload(_call("get_metadata", {"path": os.path.join(FIXTURES, ".", "structured.pdf")}, args=ROOT))
    assert plain["path"] == os.path.join(FIXTURES, ".", "structured.pdf")


def test_fill_form_writes_with_the_usual_file_mode(tmp_path):
    out_path = str(tmp_path / "filled.pdf")
    args = (*ROOT, "--root", str(tmp_path))
    name = _text_field(ACROFORM_PDF, args)
    _payload(_call("fill_form", {"path": ACROFORM_PDF, "values": {name: "x"}, "out_path": out_path}, args=args))
    umask = os.umask(0)
    os.umask(umask)
    assert os.stat(out_path).st_mode & 0o777 == 0o666 & ~umask
