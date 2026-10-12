"""One command for the required project checks; no network or media upload."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
for command in [[sys.executable, "-m", "amp.cli", "validate"],
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                ["node", "tests/score.test.mjs"],
                ["node", "--test", "tests/studio/catalog.test.mjs"],
                ["node", "--test", "tests/room-tone-transport.test.mjs", "tests/room-tone-catalog.test.mjs", "tests/room-tone-page.test.mjs"],
                ["node", "--test", *[str(path.relative_to(root)) for path in sorted((root / "tests/fx").glob("*.test.mjs"))]]]:
    subprocess.run(command, check=True, cwd=root)
