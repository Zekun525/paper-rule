"""Bundle the already-built workbench in distributable Python wheels."""

from pathlib import Path
from shutil import copy2

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithWeb(build_py):
    def run(self):
        super().run()
        if getattr(self, "editable_mode", False):
            return

        root = Path(__file__).resolve().parent
        bundle = root / "frontend" / "dist"
        index = bundle / "index.html"
        assets = bundle / "assets"
        if not index.is_file() or not assets.is_dir():
            raise RuntimeError(
                "Build the workbench before creating a distribution: "
                "run npm ci and npm run build in frontend."
            )
        if not bundle.resolve().is_relative_to(root) or assets.is_symlink():
            raise RuntimeError("The workbench must be built inside this project.")

        sources = [index, *assets.rglob("*")]
        for source in sources:
            if source.is_symlink() or not source.resolve().is_relative_to(bundle.resolve()):
                raise RuntimeError("Workbench distribution assets cannot be symbolic links.")

        destination = Path(self.build_lib) / "paperrule" / "web"
        for source in sources:
            if source.is_file():
                target = destination / source.relative_to(bundle)
                target.parent.mkdir(parents=True, exist_ok=True)
                copy2(source, target)


setup(cmdclass={"build_py": BuildWithWeb})
