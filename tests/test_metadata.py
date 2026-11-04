"""The version lives in five places; a release that bumps four of them must fail here."""

import json
from pathlib import Path
import re

import pdfluent_mcp

ROOT = Path(__file__).resolve().parent.parent


def test_versions_agree():
    version = pdfluent_mcp.__version__
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(rf'^version = "{re.escape(version)}"$', pyproject, re.M)
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server["version"] == version
    assert server["packages"][0]["version"] == version
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert plugin["version"] == version
    assert plugin["mcpServers"]["pdfluent"]["args"] == [f"pdfluent-mcp=={version}"]
    # The Open Plugins layout (Cursor Directory) reads the server from .mcp.json and skills from skills/.
    open_plugins = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert open_plugins["mcpServers"]["pdfluent"] == plugin["mcpServers"]["pdfluent"]
    assert plugin["skills"] == "./skills" and (ROOT / "skills/pdfluent/SKILL.md").is_file()
    assert f"## {version}" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_plugin_icon_is_a_square_png_in_range():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    icon = ROOT / plugin["icon"]
    assert icon.is_file() and icon.stat().st_size < 2 * 1024 * 1024
    data = icon.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    assert width == height and 512 <= width <= 2048


def test_launcher_lock_pins_this_version_with_hashes():
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    version = pdfluent_mcp.__version__
    assert re.search(rf'^name = "pdfluent-mcp"\nversion = "{re.escape(version)}"$', lock, re.M)
    assert 'hash = "sha256:' in lock


def test_privacy_policy_url_in_manifest_and_readme():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert plugin["privacyPolicyUrl"] == "https://pdfluent.com/privacy/"
    assert "](https://pdfluent.com/privacy/)" in (ROOT / "README.md").read_text(encoding="utf-8")
