"""One command for the required project checks; no network or media upload."""
import subprocess
import sys

for command in [[sys.executable, "-m", "amp.cli", "validate"],
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                ["node", "tests/score.test.mjs"]]:
    subprocess.run(command, check=True)
