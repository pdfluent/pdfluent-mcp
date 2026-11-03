"""Register the local stdio server without changing unrelated client settings."""

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Mapping, Optional, Sequence

import tomlkit

CLIENTS = ("claude-desktop", "claude-code", "cursor", "codex")
SERVER_NAME = "pdfluent"


def config_paths(home: Path, platform: str, env: Mapping[str, str]) -> dict[str, Path]:
    if platform == "darwin":
        desktop = home / "Library/Application Support/Claude/claude_desktop_config.json"
    elif platform == "win32":
        desktop = Path(env.get("APPDATA", str(home / "AppData/Roaming"))) / "Claude/claude_desktop_config.json"
    else:
        desktop = Path(env.get("XDG_CONFIG_HOME", str(home / ".config"))) / "Claude/claude_desktop_config.json"
    return {
        "claude-desktop": desktop,
        "claude-code": Path(env.get("CLAUDE_CONFIG_DIR", str(home))) / ".claude.json",
        "cursor": home / ".cursor/mcp.json",
        "codex": Path(env.get("CODEX_HOME", str(home / ".codex"))) / "config.toml",
    }


def launcher() -> tuple[str, list[str]]:
    # Do not record sys.executable from a disposable uvx environment when uvx
    # is available. An absolute uvx path also works in GUI apps with a short PATH.
    uvx = shutil.which("uvx")
    if uvx:
        return uvx, ["pdfluent-mcp"]
    return sys.executable, ["-m", "pdfluent_mcp"]


def read_config(path: Path) -> Optional[bytes]:
    if path.is_symlink():
        raise ValueError(f"{path}: refusing a symbolic link")
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def edit_config(client: str, path: Path, original: Optional[bytes], entry: dict,
                uninstall: bool, force: bool) -> Optional[bytes]:
    """Return new bytes or None for a no-op. Parse before making any writes."""
    text = original.decode("utf-8") if original is not None else ""
    is_toml = client == "codex"
    document = tomlkit.parse(text) if is_toml else (json.loads(text) if original is not None else {})
    if not isinstance(document, dict):
        raise ValueError(f"{path}: expected a configuration object")
    key = "mcp_servers" if is_toml else "mcpServers"
    servers = document.get(key, {})
    if not isinstance(servers, dict):
        raise ValueError(f"{path}: {key} must be an object/table")
    if uninstall:
        if SERVER_NAME not in servers:
            return None
        del servers[SERVER_NAME]
    else:
        if servers.get(SERVER_NAME) == entry:
            return None
        if SERVER_NAME in servers and not force:
            raise ValueError(f"{path}: pdfluent already has a different configuration; use --force to replace it")
        if key not in document:
            document[key] = tomlkit.table() if is_toml else {}
            servers = document[key]
        servers[SERVER_NAME] = entry
    result = tomlkit.dumps(document) if is_toml else json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    return result.encode("utf-8")


def atomic_write(path: Path, original: Optional[bytes], data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Refuse an edit made after planning, rather than silently replacing it.
    if read_config(path) != original:
        raise ValueError(f"{path}: configuration changed during setup; retry")
    mode = stat.S_IMODE(path.stat().st_mode) if original is not None else 0o600
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv: Sequence[str]) -> None:
    parser = argparse.ArgumentParser(prog=f"pdfluent-mcp {argv[0]}",
                                     description="Register or remove PDFluent in user MCP client configs.")
    parser.add_argument("--client", choices=(*CLIENTS, "all"), action="append",
                        help="client to configure; repeatable (default: all)")
    parser.add_argument("--root", action="append", default=[], metavar="DIR",
                        help="allowed PDF directory to pass to the server; repeatable")
    parser.add_argument("--dry-run", action="store_true", help="show planned changes without writing files")
    parser.add_argument("--uninstall", action="store_true", help="remove only the pdfluent server entry")
    parser.add_argument("--force", action="store_true", help="replace an existing pdfluent entry")
    args = parser.parse_args(list(argv[1:]))
    uninstall = argv[0] == "uninstall" or args.uninstall
    if uninstall and (args.root or args.force):
        parser.error("--root and --force apply only to installation")
    selected = args.client or ["all"]
    clients = CLIENTS if "all" in selected else tuple(dict.fromkeys(selected))
    try:
        command, server_args = launcher()
        for root in args.root:
            directory = Path(root).expanduser().resolve()
            if not directory.is_dir():
                raise ValueError(f"--root {root!r} is not a directory")
            server_args.extend(["--root", str(directory)])
        paths = config_paths(Path.home(), sys.platform, os.environ)
        plans = []
        for client in clients:
            entry = {"command": command, "args": server_args}
            if client in {"claude-code", "cursor"}:
                entry["type"] = "stdio"
            path = paths[client]
            original = read_config(path)
            data = edit_config(client, path, original, entry, uninstall, args.force)
            plans.append((client, path, original, data))
        for client, path, original, data in plans:
            action = ("remove" if uninstall else "register") if data is not None else "unchanged"
            if data is not None and not args.dry_run:
                atomic_write(path, original, data)
            print(f"{'dry-run: ' if args.dry_run else ''}{client}: {action}: {path}")
        if not uninstall:
            print(f"Server command: {json.dumps([command, *server_args])}")
            print("Restart clients to load the configuration.")
            if not args.root:
                print("No --root supplied; file access relies on client MCP roots or PDFLUENT_MCP_ROOTS.")
    except (OSError, ValueError, tomlkit.exceptions.ParseError) as error:
        parser.exit(1, f"pdfluent-mcp: {error}\n")
