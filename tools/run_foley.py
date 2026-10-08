"""Render source-timed foley buses and an isolated video audition."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amp.foley import build_foley, review_montage


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--score", default=str(Path(__file__).resolve().parents[1] / "projects/god-here/foley-score.json"))
    parser.add_argument("--no-review", action="store_true")
    args = parser.parse_args()
    score = json.loads(Path(args.score).read_text())
    manifest = build_foley(score, args.output, args.source)
    if not args.no_review:
        review_montage(args.source, args.output, score)
    print(json.dumps({"events": len(manifest["events"]), "files": manifest["files"]}))
