#!/usr/bin/env python3
"""Install this as:

git clone git@github.com:cav71/home.git
./home/bin/home.py install

"""
import os
import sys
import argparse
import copy
import logging
import subprocess
import contextlib
import shutil
import datetime
import tempfile
import json
import types
from enum import auto, Enum
from pathlib import Path

REPO = os.getenv("HOMEREPO", "https://github.com/cav71/home.git")
DEFINITIONS = {
    "HOMEROOT": "~",
    "HOMEDIR": ".home",
    "HOMEGITDIR": ".home.git",
    "CONFIGDIR": ".config/home",
}


class Status(Enum):
    FROMREPO = auto()
    FROMCHECKOUT = auto()
    INSTALLED = auto()
    READY = auto()


def loadmod(path):
    from importlib import machinery, util
    machinery.SOURCE_SUFFIXES.append("")
    spec = util.spec_from_file_location(Path(path).name, Path(path))
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    machinery.SOURCE_SUFFIXES.pop()
    return module


HOMETESTRUN = int(os.getenv("HOMETESTRUN", "0"))
for key, default in DEFINITIONS.items():
    fallback = Path(os.environ.get(key, default)).expanduser()
    globals()[key] = (Path.cwd() if key == "HOMEROOT" else HOMEROOT / fallback).resolve()


INSTALLED = False
FROMCHECKOUT = False


STATUS = None
homelib = None
gitfiles = [Path(__file__).parent.parent / ".git", Path(__file__).parent.parent / ".home"]

if (path := (HOMEDIR / "python.fns")).exists(): 
    STATUS = Status.INSTALLED
    homelib = loadmod(path)
    if (HOMEGITDIR / "patched.txt").exists():
        STATUS = Status.READY
elif all(p.exists() for p in gitfiles):
    STATUS = Status.FROMCHECKOUT
else:
    STATUS = Status.FROMREPO


if not homelib:
    class Dummy: pass
    homelib = types.ModuleType("homelib")
    homelib.Command = Dummy
    homelib.HOMEDIR = HOMEDIR
    homelib.HOMEGITDIR = HOMEGITDIR


if HOMETESTRUN or not STATUS:
    result = {
        "status": str(STATUS),
        "homelib": str(homelib),
        "envs": {
            key: str(globals().get(key))
            for key in ["HOMETESTRUN", *DEFINITIONS.keys()]
        }
    }
    print(json.dumps(result, indent=2))
    sys.exit(0 if STATUS else 1)


log = logging.getLogger(__name__)


def install():
    if STATUS == Status.FROMCHECKOUT:
        rootdir = Path(__file__).parent.parent
    elif STATUS == Status.FROMREPO::
        rootdir = Path("deleteme.home.checkout")
        if rootdir.exists():
            raise RuntimeError(f"target dir exists: {rootdir}")
        subprocess.check_call(["git", "clone", REPO, str(rootdir)])
    else:
        raise RuntimeError(f"Un-handled install {STATUS=}")


    assert not homelib.HOMEDIR.exists(), f"{homelib.HOMEDIR} present"
    assert not homelib.HOMEGITDIR.exists(), f"{homelib.HOMEGITDIR} present"

    gitdir = rootdir / ".git"
    log.info("moving %s -> %s", gitdir, homelib.HOMEGITDIR) 
    shutil.move(gitdir, homelib.HOMEGITDIR)

    homedir = rootdir
    log.info("moving %s -> %s", homedir, homelib.HOMEDIR) 
    shutil.move(homedir, homelib.HOMEDIR)

    log.info("resetting home.git")
    def grun(cmds):
        HOME = Path(os.getenv("HOME"))
        cmds = [ "git",
            "--git-dir", HOMEGITDIR,
            "--work-tree", HOMEROOT,
            *cmds
        ]
        cmds = [str(c) for c in cmds]
        subprocess.check_call(cmds)
    grun(["reset", "--hard",])
    print("setup completed, please run: ~/bin/home.py patch",
                file=sys.stderr)


class Backup(homelib.Command):
    """backup data

    This will backup system data.
    
    The config file is under:
        ~/.config/home/backup.txt

    """
    @classmethod
    def add_arguments(cls, parser):
        super(Backup, cls).add_arguments(parser)
        parser.add_argument("-n", "--dry-run", action="store_true", help="show report")
        parser.add_argument("-c", "--config", default=homelib.CONFIGDIR / "backup.txt", type=Path, help="config file")
        parser.add_argument("tarball", nargs="?", type=Path,
            default=Path(f"backup.{datetime.date.today().strftime('%Y-%m-%d')}.tar"), help="output tarball")

    @classmethod
    def run(cls, config, tarball, dry_run):
        # load configs
        repos = homelib.Tar.process_config(config)
        log.info("creating %s", tarball)
        if dry_run:
            for repo in repos:
                print(repo)
            return
        with homelib.Tar(tarball, dry_run) as tar:
            tar.create(repos)


class Patch(homelib.Command):
    TAG = "MODIFIED BY HOME PATCH"
    @classmethod
    def run(cls):
        homelib.fix_vimrc(HOMEROOT, HOMEDIR)
        homelib.fix_bashrc(HOMEDIR, CONFIGDIR)
        homelib.fix_git(HOMEROOT)
        homelib.fix_git_ignore(HOMEGITDIR)

        CONFIGDIR.mkdir(parents=True, exist_ok=True)
        homelib.fix_backup(CONFIGDIR)
        (HOMEGITDIR / "patched.txt").write_text("")


class Triplet(homelib.Command):
    """returns a (user, host, platform) triplet

    eg.
      $> home.py triplet
      antonio antonio-air darwin
    """
    @classmethod
    def run(cls):
        user, host, platform = homelib.triplet()
        print(f"{user} {host} {platform}")


class Lookup(homelib.Command):
    """lookup an item in the ~/.home hierarchy
    Performs a lookup in the ~/.home for a filename.
    Example:
      $> home.py lookup bashrc
    """
    @classmethod
    def add_arguments(cls, parser):
        super(Lookup, cls).add_arguments(parser)
        parser.add_argument("name", nargs="?", default="", help="find name in the home namespace")
        parser.add_argument("--home", action="store_true", help="lookup in the internal home namespace")

    @classmethod
    def run(cls, name, home):
        root = None if home else Path("~/.config/home")
        for candidate in homelib.Home(root).lookup(None):
            print(candidate / name.lstrip("/"))


class Edit(homelib.Command):
    """edit a file in the ~/.home hierarchy
    """
    @classmethod
    def add_arguments(cls, parser):
        super(Edit, cls).add_arguments(parser)
        parser.add_argument("name", help="find name in the home namespace")
        parser.add_argument("--home", action="store_true", help="lookup in the internal home namespace")
        parser.add_argument("--specific", action="store_true", help="use the most specific file")

    @classmethod
    def run(cls, name, home, specific):
        root = None if home else Path("~/.config/home")
        found = homelib.Home(root).lookup(name.lstrip("/"), single=False)
        if not found:
            found = [ path / name.lstrip("/") for path in homelib.Home(root).lookup(None)]
        if not found:
            raise RuntimeError(f"cannot find path for {name=}")
        target = found[0] if specific else found[-1]
        homelib.run(["vim", target])


class Help(homelib.Command):
    @classmethod
    def run(cls):
        from textwrap import dedent, indent
        pre = " "*3
        for klass in homelib.Command.__subclasses__():
            name = getattr(klass, 'NAME', klass.__name__).lower()
            description, _, text = (getattr(klass, "__doc__") or "").partition("\n") or ("","", "")
            print(f"[{name}]", end="", file=sys.stderr)
            if description:
                print(f" - {description}", file=sys.stderr)
            else:
                print(file=sys.stderr)
            if text:
                text = text[1:] if text.startswith("\n") else text
                print(homelib.indent(text.rstrip(), pre=" | "), file=sys.stderr)
    

def main():
    git = None
    if STATUS in {Status.FROMCHECKOUT, Status.FROMREPO}:
        logging.basicConfig(level=logging.DEBUG)
        if len(sys.argv) != 2 or sys.argv[1] != "install":
            print("home.py not installed, please run: home.py install", file=sys.stderr)
            sys.exit(1)
        install()
        sys.exit(0)
    elif STATUS == Status.INSTALLED:
        if len(sys.argv) != 2 or sys.argv[1] != "patch":
            print("home.py not patched, please run: home.py patch", file=sys.stderr)
            sys.exit(1)
    else:
        raise RuntimeError(f"Unhandled status {STATUS}")

    def git(args):
        env = copy.deepcopy(os.environ)
        env["GIT_CONFIG_GLOBAL"] = HOMEROOT / ".gitconfig"
        cmd = [ "git",
            f"--git-dir={HOMEGITDIR}",
            f"--work-tree={HOMEROOT}",
            *args,
        ]
        subprocess.call([str(a) for a in cmd], encoding="utf-8")
    homelib.cli(git)


if __name__ == "__main__":
    main()

