import argparse
import json
from pathlib import Path

from .audio import make_candidates, expressive_audio
from .core import generate_schedule, validate, write_json
from .render import render, remix


def main():
    parser = argparse.ArgumentParser(description="Source-addressable postproduction")
    parser.add_argument("command", choices=["validate", "audio", "render", "generate"])
    parser.add_argument("--project", default="projects/god-here")
    parser.add_argument("--source")
    parser.add_argument("--audio")
    parser.add_argument("--output", default="outputs")
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--mode", choices=["hard", "soft", "spill"], default="hard")
    parser.add_argument("--layers", action="store_true")
    parser.add_argument("--typography", action="store_true")
    parser.add_argument("--original-picture", action="store_true")
    args = parser.parse_args()
    project = Path(args.project)
    config = json.loads((project / "composition.json").read_text())
    if args.command == "validate":
        print(json.dumps(validate(config)))
    elif args.command == "audio":
        if not args.source:
            parser.error("--source is required")
        transcript = json.loads((project / "transcript.provisional.json").read_text())
        record = make_candidates(args.source, transcript, args.output)
        expressive_audio(Path(args.output) / "candidate-B.wav", config, args.output)
        print(json.dumps(record))
    elif args.command == "render":
        if not args.source or not args.audio:
            parser.error("--source and --audio are required")
        print(json.dumps(render(args.source, args.audio, config, args.output, start=args.start, end=args.end,
                         width=args.width, fields=not args.original_picture, mode=args.mode, layers=args.layers,
                         typography=args.typography)))
    elif args.command == "generate":
        if not args.source:
            parser.error("--source should point to a source-length linear workprint")
        units = json.loads((project / "units.json").read_text())["units"]
        schedule = generate_schedule(units, args.seed)
        remix(args.source, schedule, args.output)
        print(json.dumps(schedule))


if __name__ == "__main__":
    main()
