"""Produce source-bound room-pause review material without accepting its sound."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amp.roomaudit import build_audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--handles", type=float, default=1.)
    parser.add_argument("--review-rms-dbfs", type=float, default=-24.)
    parser.add_argument("--no-mp3", action="store_true")
    args = parser.parse_args()
    report = build_audit(args.source, args.inventory, args.output, handles=args.handles,
                         review_rms_dbfs=args.review_rms_dbfs, mp3=not args.no_mp3)
    print({k: report[k] for k in ("original_portion_count", "original_pool_seconds",
                                 "suggested_changed_portions", "listening_acceptance")})


if __name__ == "__main__":
    main()
