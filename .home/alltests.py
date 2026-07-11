# ~/.local/share/uv/python/cpython-3.14.3-macos-aarch64-none/bin/python -m venv .venv 
# source .venv/bin/activate
# python -m pip install pytest
# function run { pytest --confcutdir $(pwd)/.home -vvs .home/alltests.py; }
# In case of failure:
#   (cd build/second/<testname> && HOMEROOT=$(pwd) python home.py && echo ok || echo "failed [$?]")
import os
import copy
import sys
import json
import dataclasses as dc
from pathlib import Path
import shutil
import pytest
import subprocess


def check_files(base: Path, files: list[str], exists: bool = True) -> list[Path]:
    found = []
    for name in files:
        if (path := (base / name)).exists() != exists:
            found.append(path)
    return found


def test_copy_homepy(home):
    home.create()
    homepy = home.copy_homepy()
    out = json.loads(home.run([sys.executable, homepy], test=1)[1])
    assert out["status"] == "Status.FROMREPO"
    return homepy


def test_install(home, homepy=None, homerepo=None):
    homepy = homepy or test_copy_homepy(home)
    homerepo = homerepo or Path(__file__).parent.parent

    ret, out, err = home.run([sys.executable, homepy], test=0)
    assert "please run: home.py install" in err
    assert not check_files(home.path, 
        [ "bin/home.py", ".home", ".home.git", ".vimrc", ".bash_profile", ".bashrc" ], exists=False)

    ret, out, err = home.run([sys.executable, homepy, "install"], test=0, envs={"HOMEREPO": homerepo})
    assert "setup completed, please run: ~/bin/home.py patch" in err
    assert not check_files(home.path,
        [ "bin/home.py", ".home", ".home.git" ], exists=True)
    assert not check_files(home.path,
        [ ".vimrc", ".bash_profile", ".bashrc" ], exists=False)

    ret, out, err = home.run([sys.executable, homepy, "install"], test=0, envs={"HOMEREPO": Path(__file__).parent.parent})
    assert "home.py not patched, please run: home.py patch" in err

    ret, out, err = home.run([sys.executable, homepy], test=0, envs={"HOMEREPO": Path(__file__).parent.parent})
    assert "home.py not patched, please run: home.py patch" in err

    ret, out, err = home.run([sys.executable, homepy, "xyz"], test=0, envs={"HOMEREPO": Path(__file__).parent.parent})
    assert "home.py not patched, please run: home.py patch" in err


def test_install_and_patch_from_homepy_file(home, homepy=None):
    homepy = homepy or test_copy_homepy(home)

    test_install(home, homepy)

    homepy = home.copy_homepy("bin")
    ret, out, err = home.run([sys.executable, home.path / "bin/home.py"], test=0)
    assert "home.py not patched, please run: home.py patch" in err

    files = [".vimrc", ".home/.bash_profile", ".config/home/backup.txt", ".home.git/patched.txt"]
    assert not check_files(home.path, files, exists=False)

    ret, out, err = home.run([sys.executable, home.path / "bin/home.py", "patch"], test=0)
    assert not check_files(home.path, files, exists=True)


def test_clone_homepy(home):
    cmd = ["git",
        "clone", Path(__file__).parent.parent, home.create("downloads/checkout")
    ]
    subprocess.check_call([str(a) for a in cmd])

    homepy = home.path / "downloads" / "checkout" /"bin" / "home.py"
    assert homepy.exists()

    ret, out, err = home.run([sys.executable, homepy], test=1)
    out = json.loads(home.run([sys.executable, homepy], test=1)[1])
    assert (ret, out["status"]) == (0, "Status.FROMCHECKOUT")
    return homepy


def test_install_from_clone(home):
    homepy = test_clone_homepy(home)

    ret, out, err = home.run([sys.executable, homepy], test=0)
    assert "please run: home.py install" in err
    assert not check_files(home.path, 
        [ "bin/home.py", ".home", ".home.git", ".vimrc", ".bash_profile", ".bashrc" ], exists=False)
