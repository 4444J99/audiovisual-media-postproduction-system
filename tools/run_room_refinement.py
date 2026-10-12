"""Render five controlled comparisons without changing the original room rack."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amp.roomrefine import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline", help="Recovered room-rack directory; otherwise rebuild with the unchanged original engine")
    parser.add_argument("--baseline-sha256", help="Independent expected hash of recovered layered audio; otherwise authenticate it by source reconstruction")
    parser.add_argument("--dialogue", help="Optional existing full-length dialogue core for same-level context mixes")
    parser.add_argument("--selection", help="Explicit source-bound roomaudit selection; default retains all screened portions")
    parser.add_argument("--stems", action="store_true", help="Also write per-band float WAVs (adds approximately 516 MB)")
    args = parser.parse_args()
    result = build(args.source, args.inventory, args.output, baseline_dir=args.baseline,
                   dialogue_path=args.dialogue, selection_path=args.selection, write_stems=args.stems,
                   baseline_sha256=args.baseline_sha256)
    print({"report": str(Path(args.output) / "room-refinement-report.json"),
           "duration_seconds": result["duration_seconds"],
           "candidates": list(result["candidates"]), "status": result["status"]})


if __name__ == "__main__":
    main()
