"""Bundle the public native-adapter code without project media or owner inputs."""
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


RUNTIME_FILES = (
    "tools/render-fx.mjs",
    "tools/validate-execution-fx.mjs",
    "tools/run_room_stretch.py",
    "web/fx/core.mjs",
    "web/fx/catalog.mjs",
    "web/fx/visual-engine.mjs",
    "web/fx/audio-engine.mjs",
    "web/fx/workbench-state.mjs",
    "web/fx/asset-pack.mjs",
)


class BuildRuntime(build_py):
    def run(self):
        super().run()
        root = Path(__file__).resolve().parent
        for relative in RUNTIME_FILES:
            destination = Path(self.build_lib) / "amp" / "_runtime" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.copy_file(str(root / relative), str(destination))


setup(cmdclass={"build_py": BuildRuntime})
