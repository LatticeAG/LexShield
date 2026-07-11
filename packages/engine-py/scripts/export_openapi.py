#!/usr/bin/env python3
"""Export the LexShield OpenAPI schema to stdout or a file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lexshield.server.app import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export LexShield OpenAPI schema.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write schema to this file (default: stdout).",
    )
    args = parser.parse_args(argv)

    app = create_app(None)
    schema = app.openapi()
    payload = json.dumps(schema, indent=2) + "\n"

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
