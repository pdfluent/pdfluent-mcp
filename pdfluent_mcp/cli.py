"""Console dispatch; setup does not load the PDF engine or start stdio."""

import sys
from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"setup", "uninstall"}:
        from .setup import main as setup

        setup(args)
    elif args in (["--help"], ["-h"]):
        print("Usage: pdfluent-mcp [SERVER OPTIONS]\n"
              "       pdfluent-mcp setup [--client CLIENT] [--root DIR] [--dry-run]\n"
              "       pdfluent-mcp uninstall [--client CLIENT] [--dry-run]\n\n"
              "Run setup --help for registration options. Server options:")
        from .server import main as serve

        serve(args)
    else:
        from .server import main as serve

        serve(args)
