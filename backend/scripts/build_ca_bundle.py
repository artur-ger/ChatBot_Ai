from __future__ import annotations

import argparse
import ssl
from pathlib import Path

import certifi


def _read_pem(path: Path) -> str:
    text = path.read_text(encoding="ascii").strip()
    if "-----BEGIN CERTIFICATE-----" not in text:
        raise ValueError(f"Not a PEM certificate file: {path}")
    return text


def build_bundle(*, output: Path, extra_pem: list[Path]) -> None:
    parts = [_read_pem(Path(certifi.where()))]
    for path in extra_pem:
        parts.append(_read_pem(path))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts) + "\n", encoding="ascii")
    ssl.create_default_context(cafile=str(output))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("extra_pem", type=Path, nargs="+")
    args = parser.parse_args()
    build_bundle(output=args.output, extra_pem=list(args.extra_pem))
    print(args.output)


if __name__ == "__main__":
    main()
