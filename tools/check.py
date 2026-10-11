"""One command for the required project checks; no network or media upload."""
import subprocess
import sys

for command in [[sys.executable, "-m", "amp.cli", "validate"],
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                ["node", "tests/score.test.mjs"],
                ["node", "--test", "tests/room-tone-transport.test.mjs", "tests/room-tone-catalog.test.mjs", "tests/room-tone-page.test.mjs"]]:
    subprocess.run(command, check=True)
