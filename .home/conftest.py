import os
import copy
import subprocess
import dataclasses as dc
from pathlib import Path
import shutil
import pytest

BUILDIR = Path(os.getenv("BUILDIR", "build")) / "second"

@pytest.fixture(scope="function")
def home(request, tmp_path_factory):
    @dc.dataclass
    class Dir: 
        path: Path
        name: str = ""

        def __post_init__(self):
            self.path = (self.path / request.function.__name__).resolve()

        def create(self, sub: str = "") -> Path:
            path = self.path / sub
            path.mkdir(parents=True, exist_ok=True)
            return path
        
        def copy_homepy(self, subpath: str = "") -> Path:
            orig = Path(__file__).parent.parent / "bin" / "home.py"
            dst = self.path / subpath
            target = self.path / subpath / orig.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(orig, target.parent)
            return target

        def run(self, args: list[str|Path], test: int, envs: dict[str, str] | None = None) -> str:
            env = copy.deepcopy(os.environ)
            env["HOMEROOT"] = str(self.path)
            env["HOMETESTRUN"] = str(test)
            env.update({k: str(v) for k, v in (envs or {}).items()})
            p = subprocess.Popen(
                [str(a) for a in args],
                cwd=self.path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            out, err = p.communicate()
            return p.returncode, out, err

    h = Dir(tmp_path_factory._given_basetemp)
    try:
        yield h
    finally:
        #shutil.rmtree(h.path)
        pass
