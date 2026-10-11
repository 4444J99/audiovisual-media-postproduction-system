"""Render literal slowdown layers, cumulative stacks, and a spectral control."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amp.roomstretch import AUDITION_BOOST_DB, PERIODS, TARGET_LUFS, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=float, default=112.)
    parser.add_argument("--periods", type=float, nargs="+", default=PERIODS)
    parser.add_argument("--target-lufs", type=float, default=TARGET_LUFS)
    parser.add_argument("--audition-boost-db", type=float, default=AUDITION_BOOST_DB)
    parser.add_argument("--no-spectral-control", action="store_true")
    args = parser.parse_args()
    result = build(args.source, args.inventory, args.output, duration=args.duration,
                   periods=args.periods, target_lufs=args.target_lufs,
                   audition_boost_db=args.audition_boost_db,
                   spectral=not args.no_spectral_control,
                   progress=lambda message: print(message, flush=True))
    print(json.dumps({"report": str(Path(args.output) / "room-stretch-report.json"),
                      "layers": [record["id"] for record in result["layers"]],
                      "stacks": [record["id"] for record in result["stacks"]],
                      "status": result["status"]}))


if __name__ == "__main__":
    main()
