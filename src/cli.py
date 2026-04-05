from __future__ import annotations

import argparse
from typing import Sequence

from cli_demo import register_demo_commands
from cli_tools import register_tool_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="itmo-young-congress")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_demo_commands(subparsers)
    register_tool_commands(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)
