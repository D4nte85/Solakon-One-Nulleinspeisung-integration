"""Referenzprotokolle neu schreiben: python tests/regen.py [art ...]

Nur nach einer bewusst gewollten Verhaltensänderung aufrufen und den Diff prüfen.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests import scenarios  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"


def spec_sha(spec: dict) -> str:
    return hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]


def line(kind: str, spec: dict) -> str:
    rec = scenarios.run(kind, spec)
    return json.dumps({"id": spec["id"], "spec_sha": spec_sha(spec), "rec": rec},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main(kinds: list[str]) -> None:
    GOLDEN.mkdir(exist_ok=True)
    for kind in kinds or list(scenarios.COUNTS):
        lines = [line(kind, spec) for spec in scenarios.generate(kind)]
        data = ("\n".join(lines) + "\n").encode("utf-8")
        with open(GOLDEN / f"{kind}.jsonl.gz", "wb") as fh:
            with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, compresslevel=9) as gz:
                gz.write(data)
        print(f"{kind}: {len(lines)} Szenarien")


if __name__ == "__main__":
    main(sys.argv[1:])
