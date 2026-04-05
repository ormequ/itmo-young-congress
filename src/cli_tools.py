from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto import verify_merkle_proof


def _cmd_verify_proof(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    proof = [(bytes.fromhex(item["hash"]), item["left"]) for item in payload["proof"]]
    valid = verify_merkle_proof(
        bytes.fromhex(payload["leaf"]),
        proof,
        bytes.fromhex(payload["root"]),
    )
    return 0 if valid else 1


def register_tool_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    verify_parser = subparsers.add_parser("verify-proof")
    # Path to JSON input containing a leaf, proof and Merkle root.
    verify_parser.add_argument("--input", required=True)
    verify_parser.set_defaults(handler=_cmd_verify_proof)
