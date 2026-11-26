"""The plugin folders submitted to the Claude directory (plugins/pdfluent-hosted, -extract and -pdf).

The directory refuses a local MCP server from an unverified publisher, a secret in a header,
and files it cannot inspect. These tests pin what the folder may hold; the local server and its
fixtures stay in the repository root, outside the folder.
"""

import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parent.parent
# name -> the one MCP endpoint its server points at. The hosted bundle stays for existing installs (full tool set).
URLS = {
    "pdfluent-hosted": "https://api.pdfluent.com/mcp",
    "pdfluent-extract": "https://api.pdfluent.com/mcp/extract",
    "pdfluent-pdf": "https://api.pdfluent.com/mcp/pdf",
}
TEXT_SUFFIXES = {".json", ".md", ".txt", ""}
LAUNCHERS = re.compile(r"\b(npx|bunx|pnpm|yarn|uvx|pipx|uv|python3?|node|bash|sh)\b")


def _files(bundle):
    return [p for p in bundle.rglob("*") if p.is_file() or p.is_symlink()]


def _manifest(bundle):
    return json.loads((bundle / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))


def _servers(bundle):
    return json.loads((bundle / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]


@pytest.fixture(params=sorted(URLS))
def bundle(request):
    path = ROOT / "plugins" / request.param
    assert path.is_dir(), f"{request.param} is not a folder"
    return path


def test_the_only_server_is_the_remote_https_endpoint(bundle):
    servers = _servers(bundle)
    assert list(servers) == [bundle.name]
    server = servers[bundle.name]
    assert server["type"] == "http" and server["url"] == URLS[bundle.name]
    assert not {"command", "args"} & set(server), "a launch command is a local server"
    assert "mcpServers" not in _manifest(bundle), ".mcp.json loads on its own; declaring it twice loads it twice"


def test_the_key_comes_from_a_sensitive_user_setting_and_nowhere_else(bundle):
    option = _manifest(bundle)["userConfig"]["api_key"]
    assert option["sensitive"] is True and option["required"] is True
    headers = _servers(bundle)[bundle.name]["headers"]
    assert headers == {"x-api-key": "${user_config.api_key}"}


def test_no_file_holds_a_real_looking_key_or_reads_one_from_the_environment(bundle):
    for path in _files(bundle):
        if path.suffix == ".png":
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"pdfl_[A-Za-z0-9_-]{10,}", text), path
        assert "PDFLUENT_API_KEY" not in text, f"{path} reads the user's environment"
        assert "$PDFLUENT" not in text, path


def test_the_folder_ships_only_what_the_directory_accepts(bundle):
    files = _files(bundle)
    assert 0 < len(files) <= 512
    for path in files:
        assert not path.is_symlink(), path
        rel = path.relative_to(bundle)
        assert path.suffix in TEXT_SUFFIXES | {".png"}, rel
        assert path.stat().st_size < (2 * 1024 * 1024 if path.suffix == ".png" else 256 * 1024), rel
        assert "fixtures" not in rel.parts and "tests" not in rel.parts and "scripts" not in rel.parts, rel
        assert path.name not in {".DS_Store", "Thumbs.db", "desktop.ini"}, rel
        if path.name == "LICENSE":
            continue
        if path.suffix in {".json", ".md"}:
            assert not LAUNCHERS.search(path.read_text(encoding="utf-8")) or path.suffix == ".md", rel
    assert not list(bundle.rglob("*.pdf")), "no document ships in the bundle"


def test_readme_licence_and_icon_the_validator_requires(bundle):
    readme = (bundle / "README.md").read_text(encoding="utf-8")
    prose = re.sub(r"```.*?```", "", readme, flags=re.S)
    assert len(prose.split()) >= 40
    assert "YOUR_API_KEY" in readme
    assert (bundle / "LICENSE").read_text(encoding="utf-8") == (ROOT / "LICENSE").read_text(encoding="utf-8")
    icon = bundle / _manifest(bundle)["icon"]
    data = icon.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    assert width == height and 512 <= width <= 2048
    assert _manifest(bundle)["privacyPolicyUrl"] == "https://pdfluent.com/privacy/"


def test_the_encrypted_fixture_stays_out_of_the_bundle_and_the_local_server_stays_outside_it(bundle):
    assert (ROOT / "tests/fixtures/encrypted-user-secret.pdf").is_file()
    assert not any(bundle in p.parents for p in (ROOT / "tests/fixtures").rglob("*"))
    assert (ROOT / "pdfluent_mcp/server.py").is_file() and not (bundle / "pdfluent_mcp").exists()


def test_the_marketplace_lists_all_three_bundles_at_their_folders():
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    sources = {p["name"]: p["source"] for p in market["plugins"]}
    for name in URLS:
        assert sources[name] == f"./plugins/{name}"
    for entry in market["plugins"]:
        if entry["name"] in URLS:
            assert entry["description"] and "\u2014" not in entry["description"]


def test_the_manifest_names_match_their_folder_and_the_skill_they_ship(bundle):
    manifest = _manifest(bundle)
    assert manifest["name"] == bundle.name
    skill = (bundle / "skills" / bundle.name / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith(f"---\nname: {bundle.name}\n")
    assert URLS[bundle.name] in skill or bundle.name == "pdfluent-hosted"


def test_no_text_file_uses_an_em_dash(bundle):
    for path in _files(bundle):
        if path.suffix != ".png":
            assert "\u2014" not in path.read_text(encoding="utf-8"), path


# The tools each product endpoint serves (services/gateway/src/gateway/mcp-scope.ts in the XFA repository):
# Extract is the extract.* and ai.* groups plus partition, compat.unstructured_general, search and info;
# PDF is everything else plus info.
# The tool list of the hosted API, copied from the registry in the XFA repository (the tools of /mcp, 46 on 25 November 2026);
# the gateway's own test keeps the split in step with the registry.
TOOLS = {
    "ai_classify",
    "ai_query",
    "ai_summarize",
    "barcodes_read",
    "compat_unstructured_general",
    "convert_email",
    "convert_html",
    "convert_office",
    "convert_template",
    "convert_to_images",
    "convert_to_pptx",
    "convert_to_xlsx",
    "convert_url",
    "extract_chunks",
    "extract_embeddings",
    "extract_images",
    "extract_markdown",
    "extract_schema",
    "extract_tables",
    "extract_text",
    "forms_export",
    "forms_fields",
    "forms_fill",
    "forms_import",
    "forms_xfa_flatten",
    "info",
    "ocr_searchable",
    "partition",
    "pdf_compress",
    "pdf_decrypt",
    "pdf_encrypt",
    "pdf_flatten",
    "pdf_merge",
    "pdf_metadata",
    "pdf_page_boxes",
    "pdf_pages",
    "pdf_redact",
    "pdf_replace_text",
    "pdf_split",
    "pdf_watermark",
    "pdfa_convert",
    "pdfa_validate",
    "pdfua_check",
    "search",
    "signatures_verify",
    "zugferd_create",
}


def _tool_names():
    return set(TOOLS)


def _extract_scope(name):
    return name.split("_")[0] in {"extract", "ai"} or name in {"partition", "compat_unstructured_general", "search", "info"}


@pytest.mark.parametrize("name", ["pdfluent-extract", "pdfluent-pdf"])
def test_a_scoped_skill_names_only_tools_its_endpoint_serves(name):
    skill = (ROOT / "plugins" / name / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    known = _tool_names()
    named = {t for t in re.findall(r"`([a-z0-9]+(?:_[a-z0-9]+)+|partition|search|info)`", skill) if t in known}
    assert named, "the skill names no tool"
    for tool in named:
        if tool == "info":
            continue
        assert _extract_scope(tool) == (name == "pdfluent-extract"), f"{tool} is not on the {name} endpoint"


def test_the_two_products_split_the_tool_list_and_share_only_info():
    known = _tool_names()
    extract = {t for t in known if _extract_scope(t)}
    pdf = (known - extract) | {"info"}
    assert extract & pdf == {"info"}
    assert extract | pdf == known
    assert {"extract_markdown", "partition", "ai_query", "search"} <= extract
    assert {"pdf_merge", "forms_fill", "convert_html", "ocr_searchable"} <= pdf


def test_the_manifest_carries_the_support_documentation_and_terms_urls(bundle):
    manifest = _manifest(bundle)
    assert manifest["supportUrl"] == "https://pdfluent.com/support/"
    assert manifest["documentationUrl"] == "https://pdfluent.com/docs/api/"
    assert manifest["termsOfServiceUrl"] == "https://pdfluent.com/terms/"
