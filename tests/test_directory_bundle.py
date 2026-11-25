"""The plugin folder submitted to the Claude directory (plugins/pdfluent-hosted).

The directory refuses a local MCP server from an unverified publisher, a secret in a header,
and files it cannot inspect. These tests pin what the folder may hold; the local server and its
fixtures stay in the repository root, outside the folder.
"""

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "plugins" / "pdfluent-hosted"
TEXT_SUFFIXES = {".json", ".md", ".txt", ""}
LAUNCHERS = re.compile(r"\b(npx|bunx|pnpm|yarn|uvx|pipx|uv|python3?|node|bash|sh)\b")


def _files():
    return [p for p in BUNDLE.rglob("*") if p.is_file() or p.is_symlink()]


def _manifest():
    return json.loads((BUNDLE / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))


def _servers():
    return json.loads((BUNDLE / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]


def test_the_only_server_is_the_remote_https_endpoint():
    servers = _servers()
    assert list(servers) == ["pdfluent-hosted"]
    server = servers["pdfluent-hosted"]
    assert server["type"] == "http" and server["url"] == "https://api.pdfluent.com/mcp"
    assert not {"command", "args"} & set(server), "a launch command is a local server"
    assert "mcpServers" not in _manifest(), ".mcp.json loads on its own; declaring it twice loads it twice"


def test_the_key_comes_from_a_sensitive_user_setting_and_nowhere_else():
    option = _manifest()["userConfig"]["api_key"]
    assert option["sensitive"] is True and option["required"] is True
    headers = _servers()["pdfluent-hosted"]["headers"]
    assert headers == {"x-api-key": "${user_config.api_key}"}


def test_no_file_holds_a_real_looking_key_or_reads_one_from_the_environment():
    for path in _files():
        if path.suffix == ".png":
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"pdfl_[A-Za-z0-9_-]{10,}", text), path
        assert "PDFLUENT_API_KEY" not in text, f"{path} reads the user's environment"
        assert "$PDFLUENT" not in text, path


def test_the_folder_ships_only_what_the_directory_accepts():
    files = _files()
    assert 0 < len(files) <= 512
    for path in files:
        assert not path.is_symlink(), path
        rel = path.relative_to(BUNDLE)
        assert path.suffix in TEXT_SUFFIXES | {".png"}, rel
        assert path.stat().st_size < (2 * 1024 * 1024 if path.suffix == ".png" else 256 * 1024), rel
        assert "fixtures" not in rel.parts and "tests" not in rel.parts and "scripts" not in rel.parts, rel
        assert path.name not in {".DS_Store", "Thumbs.db", "desktop.ini"}, rel
        if path.name == "LICENSE":
            continue
        if path.suffix in {".json", ".md"}:
            assert not LAUNCHERS.search(path.read_text(encoding="utf-8")) or path.suffix == ".md", rel
    assert not list(BUNDLE.rglob("*.pdf")), "no document ships in the bundle"


def test_readme_licence_and_icon_the_validator_requires():
    readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
    prose = re.sub(r"```.*?```", "", readme, flags=re.S)
    assert len(prose.split()) >= 40
    assert "YOUR_API_KEY" in readme
    assert (BUNDLE / "LICENSE").read_text(encoding="utf-8") == (ROOT / "LICENSE").read_text(encoding="utf-8")
    icon = BUNDLE / _manifest()["icon"]
    data = icon.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    assert width == height and 512 <= width <= 2048
    assert _manifest()["privacyPolicyUrl"] == "https://pdfluent.com/privacy/"


def test_the_encrypted_fixture_stays_out_of_the_bundle_and_the_local_server_stays_outside_it():
    assert (ROOT / "tests/fixtures/encrypted-user-secret.pdf").is_file()
    assert not any(BUNDLE in p.parents for p in (ROOT / "tests/fixtures").rglob("*"))
    assert (ROOT / "pdfluent_mcp/server.py").is_file() and not (BUNDLE / "pdfluent_mcp").exists()
    # The marketplace lists both plugins; the directory submission is the hosted folder alone.
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert {p["name"]: p["source"] for p in market["plugins"]}["pdfluent-hosted"] == "./plugins/pdfluent-hosted"
