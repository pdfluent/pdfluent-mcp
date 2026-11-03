"""Client-format acceptance tests. All configs are synthetic, under tmp_path."""

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest
import tomlkit

from pdfluent_mcp import cli
from pdfluent_mcp import setup


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    for name in ("APPDATA", "XDG_CONFIG_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/tools with spaces/uvx")
    return home, setup.config_paths(home, sys.platform, {})


def load(client, path):
    text = path.read_text(encoding="utf-8")
    return tomlkit.parse(text) if client == "codex" else json.loads(text)


def seed(client, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if client == "codex":
        path.write_text('# keep this comment\nmodel = "keep-model"\n[mcp_servers.other]\ncommand = "keep-other"\n', encoding="utf-8")
    else:
        path.write_text(json.dumps({"theme": "keep-theme", "projects": {"/work": {"keep": True}},
                                    "mcpServers": {"other": {"command": "keep-other"}}}), encoding="utf-8")


@pytest.mark.parametrize("client", setup.CLIENTS)
def test_client_format_roundtrip(client, sandbox, tmp_path, capsys):
    _, paths = sandbox
    path = paths[client]
    seed(client, path)
    before = load(client, path)
    root = tmp_path / "PDF files"
    root.mkdir()
    cli.main(["setup", "--client", client, "--root", str(root)])
    after = load(client, path)
    key = "mcp_servers" if client == "codex" else "mcpServers"
    assert after[key]["pdfluent"]["command"] == "/tools with spaces/uvx"
    assert after[key]["pdfluent"]["args"] == ["pdfluent-mcp", "--root", str(root.resolve())]
    if client in {"claude-code", "cursor"}:
        assert after[key]["pdfluent"]["type"] == "stdio"
    after[key].pop("pdfluent")
    assert after == before
    if client == "codex":
        assert "# keep this comment" in path.read_text()
    installed = path.read_bytes()
    cli.main(["setup", "--client", client, "--root", str(root)])
    assert "unchanged" in capsys.readouterr().out
    assert path.read_bytes() == installed
    cli.main(["uninstall", "--client", client, "--dry-run"])
    assert path.read_bytes() == installed
    cli.main(["setup", "--client", client, "--uninstall"])
    assert load(client, path) == before
    removed = path.read_bytes()
    cli.main(["uninstall", "--client", client])
    assert path.read_bytes() == removed


@pytest.mark.parametrize("client", setup.CLIENTS)
def test_missing_config_dry_run_install_uninstall(client, sandbox):
    _, paths = sandbox
    path = paths[client]
    cli.main(["setup", "--client", client, "--dry-run"])
    assert not path.exists()
    cli.main(["uninstall", "--client", client])
    assert not path.exists()
    cli.main(["setup", "--client", client])
    assert path.exists()
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    cli.main(["uninstall", "--client", client])
    assert "pdfluent" not in load(client, path).get("mcp_servers" if client == "codex" else "mcpServers", {})


def test_all_default_and_selection(sandbox):
    _, paths = sandbox
    cli.main(["setup", "--client", "cursor", "--client", "cursor"])
    assert paths["cursor"].exists()
    assert all(not p.exists() for c, p in paths.items() if c != "cursor")
    cli.main(["setup"])
    assert all(p.exists() for p in paths.values())
    cli.main(["uninstall", "--client", "all"])
    assert all("pdfluent" not in p.read_text() for p in paths.values())


@pytest.mark.parametrize("client", setup.CLIENTS)
def test_conflict_requires_force(client, sandbox):
    _, paths = sandbox
    path = paths[client]
    seed(client, path)
    cli.main(["setup", "--client", client])
    saved = path.read_bytes()
    with pytest.raises(SystemExit) as error:
        cli.main(["setup", "--client", client, "--root", str(path.parent)])
    assert error.value.code == 1
    assert path.read_bytes() == saved
    cli.main(["setup", "--client", client, "--root", str(path.parent), "--force"])
    assert path.read_bytes() != saved


@pytest.mark.parametrize("client,bad", [("claude-desktop", "{"), ("claude-code", "[]"),
                                       ("cursor", '{"mcpServers": []}'), ("codex", "[broken")])
def test_bad_config_preflight_writes_nothing(client, bad, sandbox):
    home, paths = sandbox
    path = paths[client]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bad)
    saved = {p: p.read_bytes() for p in home.rglob("*") if p.is_file()}
    with pytest.raises(SystemExit) as error:
        cli.main(["setup"])
    assert error.value.code == 1
    assert {p: p.read_bytes() for p in home.rglob("*") if p.is_file()} == saved


@pytest.mark.parametrize("platform,desktop", [
    ("darwin", "Library/Application Support/Claude/claude_desktop_config.json"),
    ("win32", "AppData/Roaming/Claude/claude_desktop_config.json"),
    ("linux", ".config/Claude/claude_desktop_config.json"),
])
def test_platform_paths(tmp_path, platform, desktop):
    assert setup.config_paths(tmp_path, platform, {}) == {
        "claude-desktop": tmp_path / desktop,
        "claude-code": tmp_path / ".claude.json",
        "cursor": tmp_path / ".cursor/mcp.json",
        "codex": tmp_path / ".codex/config.toml",
    }


def test_config_overrides(tmp_path):
    env = {"APPDATA": str(tmp_path / "appdata"), "CODEX_HOME": str(tmp_path / "codex"),
           "XDG_CONFIG_HOME": str(tmp_path / "xdg"), "CLAUDE_CONFIG_DIR": str(tmp_path / "claude")}
    assert setup.config_paths(tmp_path, "win32", env)["claude-desktop"] == tmp_path / "appdata/Claude/claude_desktop_config.json"
    paths = setup.config_paths(tmp_path, "linux", env)
    assert paths["claude-desktop"] == tmp_path / "xdg/Claude/claude_desktop_config.json"
    assert paths["codex"] == tmp_path / "codex/config.toml"
    assert paths["claude-code"] == tmp_path / "claude/.claude.json"


def test_fallback_launcher(monkeypatch):
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    assert setup.launcher() == (sys.executable, ["-m", "pdfluent_mcp"])


def test_multiple_roots(sandbox, tmp_path):
    _, paths = sandbox
    cli.main(["setup", "--client", "cursor", "--root", str(tmp_path), "--root", str(tmp_path / "home")])
    entry = load("cursor", paths["cursor"])["mcpServers"]["pdfluent"]
    assert entry["args"] == ["pdfluent-mcp", "--root", str(tmp_path.resolve()), "--root", str((tmp_path / "home").resolve())]


def test_invalid_root_writes_nothing(sandbox):
    home, _ = sandbox
    with pytest.raises(SystemExit) as error:
        cli.main(["setup", "--root", str(home / "missing")])
    assert error.value.code == 1
    assert list(home.iterdir()) == []


def test_uninstall_rejects_install_options(sandbox):
    with pytest.raises(SystemExit) as error:
        cli.main(["uninstall", "--force"])
    assert error.value.code == 2


def test_atomic_refuses_stale_snapshot(tmp_path):
    path = tmp_path / "config.json"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed during setup"):
        setup.atomic_write(path, b"before", b"replacement")
    assert path.read_bytes() == b"changed"


def test_atomic_failure_preserves_config(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_bytes(b"original")
    def fail(*args):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(setup.os, "replace", fail)
    with pytest.raises(OSError, match="simulated"):
        setup.atomic_write(path, b"original", b"replacement")
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions and symlinks")
def test_permissions_and_symlink(sandbox, tmp_path):
    _, paths = sandbox
    path = paths["cursor"]
    seed("cursor", path)
    path.chmod(0o640)
    cli.main(["setup", "--client", "cursor"])
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    target = tmp_path / "target"
    target.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(SystemExit) as error:
        cli.main(["uninstall", "--client", "cursor"])
    assert error.value.code == 1
    assert "pdfluent" in target.read_text()


def test_console_and_module_entrypoint(tmp_path):
    # Only a synthetic Codex config is selected. No real client files.
    env = dict(os.environ, CODEX_HOME=str(tmp_path / "codex"))
    executable = Path(sys.executable).parent / ("pdfluent-mcp.exe" if os.name == "nt" else "pdfluent-mcp")
    for command in ([str(executable)], [sys.executable, "-m", "pdfluent_mcp"]):
        result = subprocess.run([*command, "setup", "--client", "codex", "--dry-run"], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert "codex" in result.stdout
        assert "dry-run" in result.stdout
        assert not (tmp_path / "codex").exists()


def test_server_dispatch_preserved(monkeypatch):
    import types
    calls = []
    monkeypatch.setitem(sys.modules, "pdfluent_mcp.server", types.SimpleNamespace(main=lambda args: calls.append(args)))
    cli.main(["--root", "/example"])
    assert calls == [["--root", "/example"]]
