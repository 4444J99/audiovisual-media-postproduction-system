import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Source-addressable postproduction")
    parser.add_argument("command", choices=["validate", "audio", "render", "generate", "revision", "replay", "track", "execute"])
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
    parser.add_argument("--recipe")
    parser.add_argument("--session")
    parser.add_argument("--track")
    parser.add_argument("--roi", nargs=4, type=float)
    parser.add_argument("--binding")
    parser.add_argument("--media-index", action="append", default=[])
    parser.add_argument("--locations")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "execute":
        from .execution import execute, preflight
        from .media_resolver import ContractError, read_json
        if not args.binding:
            parser.error("execute requires --binding")
        supplied_options = {arg.split("=", 1)[0] for arg in sys.argv[1:] if arg.startswith("--")}
        if supplied_options - {"--binding", "--media-index", "--locations", "--output", "--dry-run"}:
            parser.error("execute accepts binding/resolution options only; native settings belong in the binding")
        if not args.dry_run and "--output" not in supplied_options:
            parser.error("execute requires an explicit fresh --output directory unless --dry-run is used")
        try:
            plan = preflight(args.binding,
                             locations=read_json(args.locations, role="locations") if args.locations else None,
                             inventories=[read_json(p, role="media-index") for p in args.media_index])
            result = plan.receipt() if args.dry_run else execute(plan, args.output)
        except ContractError as exc:
            print(json.dumps({"schema_version": "amps.execution-receipt.v1", "status": "blocked",
                              "error": {"code": exc.code, "role": exc.role}, "artistic_acceptance": "pending"}))
            return 2
        except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, StopIteration):
            # Never expose an owner locator or native traceback through this public interface.
            print(json.dumps({"schema_version": "amps.execution-receipt.v1", "status": "blocked",
                              "error": {"code": "unsupported_dependency_or_contract"}, "artistic_acceptance": "pending"}))
            return 2
        print(json.dumps(result, indent=2))
        return 0
    from .audio import make_candidates, expressive_audio
    from .core import generate_schedule, validate, write_json
    from .render import render, remix
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
    elif args.command == "track":
        from .revision import track_region
        if not args.source or args.end is None or not args.roi:
            parser.error('track requires --source, --end, and --roi')
        record=track_region(args.source,round(args.start*config['fps']),round(args.end*config['fps']),args.roi,args.output,config['fps'])
        print(json.dumps({'tracked_frames':len(record['rows']),'output':args.output}))
    else:
        from .revision import render_revision, validate_session
        if not args.source or not args.audio:
            parser.error('revision/replay requires --source and --audio')
        if args.command=='revision' and not args.recipe:
            parser.error('revision requires --recipe')
        if args.command=='replay' and not args.session:
            parser.error('replay requires --session')
        recipe=json.loads(Path(args.recipe).read_text()) if args.recipe else {
            'schema_version':'1.0','source_sha256':config['source_sha256'],
            'segments':[{'source_start_frame':round(args.start*config['fps']),
                         'source_end_frame':round((args.end or 112)*config['fps']),
                         'output_frames':round(((args.end or 112)-args.start)*config['fps'])}],
            'animated_typography':True}
        session=json.loads(Path(args.session).read_text()) if args.session else None
        if args.session:
            from .core import probe
            validate_session(session, config, float(probe(args.source)['format']['duration']))
        track=json.loads(Path(args.track).read_text()) if args.track else None
        print(json.dumps(render_revision(args.source,args.audio,config,recipe,args.output,session,track,args.width)))


if __name__ == "__main__":
    raise SystemExit(main())
