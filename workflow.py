#!/usr/bin/env python3
"""Bundle the portable Markdown contract without importing a runtime adapter."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
DOCUMENTS = ("WORKFLOW.md", "CODE_STRUCTURE.md", "PROOF.md")


def render():
    return "\n\n---\n\n".join(
        (ROOT / name).read_text(encoding="utf-8").strip() for name in DOCUMENTS
    ) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Create a new Markdown file; never overwrite an existing file")
    args = parser.parse_args()
    try:
        contract = render()
        if args.output:
            with args.output.open("x", encoding="utf-8") as output:
                output.write(contract)
        else:
            sys.stdout.write(contract)
    except OSError as exc:
        parser.exit(1, f"Could not export workflow: {exc}\n")


if __name__ == "__main__":
    main()
