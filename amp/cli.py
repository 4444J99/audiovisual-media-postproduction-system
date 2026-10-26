import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Source-addressable postproduction")
    parser.add_argument("command", choices=["validate", "qualify", "audio", "render", "generate", "revision", "replay", "track", "execute", "performance"])
    parser.add_argument("--composition", "--project", dest="project",
                        help="Composition directory, registered ID or alias; --project remains compatible")
    parser.add_argument("--source")
    parser.add_argument("--audio")
    parser.add_argument("--output")
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--generation-mode", choices=["source-mixture", "linguistic"], default="source-mixture")
    parser.add_argument("--qualification", help="Source-bound review record; defaults to PROJECT/qualification.json")
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
    parser.add_argument("--operation", choices=["new", "replay", "inspect"], default="new")
    parser.add_argument("--corpus")
    parser.add_argument("--profile")
    parser.add_argument("--history")
    parser.add_argument("--identity")
    parser.add_argument("--duration-frames", type=int)
    args = parser.parse_args()
    performance_options = {"--operation", "--corpus", "--profile", "--history", "--identity", "--duration-frames"}
    supplied_options = {arg.split("=", 1)[0] for arg in sys.argv[1:] if arg.startswith("--")}
    if args.command == "performance":
        from .composition.performance_cli import run
        return run(args, supplied_options)
    if supplied_options & performance_options:
        parser.error("performance options require the performance command")
    if args.command in ("revision", "replay"):
        if args.output is None:
            parser.error("revision/replay requires an explicit --output file, for example outputs/revision.mp4")
        destination = Path(args.output)
        if destination.is_dir() or not destination.suffix:
            parser.error("revision/replay --output must be a movie filename with an extension")
    elif args.command == "track":
        if args.output is None:
            parser.error("track requires an explicit --output JSON file, for example outputs/track.json")
        destination = Path(args.output)
        if destination.is_dir() or destination.suffix.lower() != ".json":
            parser.error("track --output must be a .json filename")
    elif args.output is None:
        args.output = "outputs"
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
            document = read_json(args.binding, role="binding", limit=1024*1024)
            if isinstance(document, dict) and document.get("schema_version") == "amps.study.v1":
                from .studies.review_artifacts import run_cli
                result = run_cli(document,
                    locations=read_json(args.locations, role="locations") if args.locations else None,
                    inventories=[read_json(p, role="media-index") for p in args.media_index],
                    output=Path(args.output), dry_run=args.dry_run)
                print(json.dumps(result, indent=2))
                return 0
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
    from .composition import resolve_composition
    try:
        project = resolve_composition(args.project)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    if args.command in ("qualify", "generate"):
        from fractions import Fraction
        from .generation import frame_units, generate_schedule
        from .qualification import audit_qualification
        review_path = Path(args.qualification) if args.qualification else project / "qualification.json"
        try:
            units = json.loads((project / "units.json").read_text())["units"]
            config = json.loads((project / "composition.json").read_text())
            source, qualification = None, None
            if args.command == "qualify" or args.generation_mode == "linguistic":
                registrations = json.loads((project / "source-registration.json").read_text())["sources"]
                matching = [item for item in registrations if item["sha256"] == config["source_sha256"]]
                if len(matching) != 1:
                    raise ValueError("Expected one registered composition source")
                source = {key: matching[0][key] for key in ("sha256", "frame_count", "fps")}
                if Fraction(source["fps"]["numerator"], source["fps"]["denominator"]) != Fraction(str(config["fps"])):
                    raise ValueError("Composition and registration timebases disagree")
                qualification = json.loads(review_path.read_text())
            elif args.qualification:
                raise ValueError("Use --generation-mode linguistic with --qualification")
            if args.command == "qualify":
                result = audit_qualification(qualification, source=source, units=frame_units(units, source))
            else:
                result = generate_schedule(units, args.seed, generation_mode=args.generation_mode,
                                           qualification=qualification, source=source)
                if not args.dry_run:
                    if not args.source:
                        raise ValueError("generate requires --source unless --dry-run is used")
                    from .core import require_distinct_outputs
                    from .render import remix
                    protected = [project / name for name in ("units.json", "composition.json", "source-registration.json")]
                    protected.append(review_path)
                    require_distinct_outputs(protected, [args.output, Path(args.output).with_suffix(".schedule.json")])
                    remix(args.source, result, args.output)
        except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}))
            return 2
        print(json.dumps(result, indent=2))
        return 0
    from .audio import make_candidates, expressive_audio, expressive_output_paths
    from .core import validate, write_json, require_distinct_outputs
    from .render import render, remix
    config = json.loads((project / "composition.json").read_text())
    if args.command == "validate":
        print(json.dumps(validate(config)))
    elif args.command == "audio":
        if not args.source:
            parser.error("--source is required")
        protected = (args.source, project / "composition.json", project / "transcript.provisional.json")
        require_distinct_outputs(protected, expressive_output_paths(config, args.output))
        transcript = json.loads((project / "transcript.provisional.json").read_text())
        record = make_candidates(args.source, transcript, args.output, protected_inputs=protected)
        expressive_audio(Path(args.output) / "candidate-B.wav", config, args.output, protected_inputs=protected)
        print(json.dumps(record))
    elif args.command == "render":
        if not args.source or not args.audio:
            parser.error("--source and --audio are required")
        print(json.dumps(render(args.source, args.audio, config, args.output, start=args.start, end=args.end,
                         width=args.width, fields=not args.original_picture, mode=args.mode, layers=args.layers,
                         typography=args.typography)))
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
