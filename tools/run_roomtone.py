import argparse
import json
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amp.roomtone import create_roomtone
from amp.core import sha256

REVISION = "1e261b036686cd0017d500ee96acd1c4ba572a9d"
MODEL_HASH = "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"

parser = argparse.ArgumentParser(description="Assemble nonlooping room tone from every screened source pause")
parser.add_argument("--source", required=True)
parser.add_argument("--model", required=True)
parser.add_argument("--transcript", default="projects/god-here/transcript.provisional.json")
parser.add_argument("--output", required=True)
parser.add_argument("--duration", type=float, default=112)
parser.add_argument("--seed", type=int, default=6971)
args = parser.parse_args()
model = Path(args.model)
if not model.exists():
    model.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://raw.githubusercontent.com/snakers4/silero-vad/{REVISION}/src/silero_vad/data/silero_vad.onnx"
    model.write_bytes(urllib.request.urlopen(url, timeout=90).read())
if sha256(model) != MODEL_HASH:
    raise ValueError("Silero model does not match pinned checkpoint")
result = create_roomtone(args.source, json.loads(Path(args.transcript).read_text()), args.model,
                         args.output, duration=args.duration, seed=args.seed)
print(json.dumps({k: result[k] for k in ["pause_count", "eligible_portion_count", "eligible_source_seconds",
                                        "duration_seconds", "every_eligible_portion_used", "sha256"]}))
