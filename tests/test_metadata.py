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
