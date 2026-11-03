"""Activate prepared packages and a private mutable user scope."""

import os
import json
from pathlib import Path
import sys

from .common import HERE, STATE, clean_env, load, native, run


def realize(root, companion, target="environment"):
    state = root / STATE
    state.mkdir(parents=True, exist_ok=True)
    output = state / (target + ".json")
    run(
        [
            "nix",
            "build",
            "--impure",
            "--file",
            HERE / "nix/realize.nix",
            "--argstr",
            "project",
            root,
            "--argstr",
            "companion",
            companion,
            "--argstr",
            "target",
            target,
            "--arg",
            "profile",
            "true",
            "--argstr",
            "sdk",
            os.environ["RACKET_PURIFIER_SDK"],
            "--out-link",
            output,
        ],
        stdout=sys.stderr,
    )
    return Path(json.loads(output.read_text())["output"])


def execute(root, companion, args, tool=None):
    if not companion.exists():
        print(
            "warning: no racket-purifier lockfile; using ordinary impure resolution",
            file=sys.stderr,
        )
        command = [native(tool), *args] if tool else args
        os.execvpe(
            str(command[0]), [str(value) for value in command], os.environ.copy()
        )
    data = load(root, companion)
    environment = realize(root, companion)
    state = root / STATE / "session"
    env = clean_env(state)
    addon = state / "addon"
    addon.mkdir(exist_ok=True)
    env.update(
        {
            "PLTCONFIGDIR": str(environment / "config"),
            "PLTCOLLECTS": os.environ["RACKET_PURIFIER_COLLECTS"],
            "PLTADDONDIR": str(addon),
            "RACKET_PURIFIER_PROJECT": str(root),
            "RACKET_PURIFIER_LOCK": str(companion),
        }
    )
    env["PATH"] = os.environ["RACKET_PURIFIER_SDK"] + "/bin:" + env["PATH"]
    if tool == "raco" and args[:1] == ["pkg"]:
        if args[1:2] in (
            ["update"],
            ["remove"],
            ["uninstall"],
            ["migrate"],
            ["config"],
        ):
            raise ValueError(
                "This command changes resolution; edit info.rkt and run racket-purifier lock --update"
            )
        if args[1:2] == ["install"]:
            # Keep native linking/setup semantics, while limiting installation to the locked application.
            options = args[2:]
            paths = []
            normalized = []
            selected_name = None
            index = 0
            value_options = {
                "--deps",
                "--jobs",
                "-j",
                "--checksum",
                "--name",
                "-n",
                "--scope",
                "--type",
                "-t",
            }
            while index < len(options):
                option = options[index]
                if option in (
                    "--scope-dir",
                    "--installation",
                    "-i",
                    "--catalog",
                    "--clone",
                    "--update-deps",
                ):
                    raise ValueError(
                        "Locked installation uses the project's private scope and prepared dependencies"
                    )
                if option in value_options:
                    if index + 1 >= len(options):
                        raise ValueError("Missing value for " + option)
                    value = options[index + 1]
                    if option in ("--name", "-n"):
                        selected_name = value
                    if option == "--scope" and value != "user":
                        raise ValueError(
                            "Locked installation uses the project's private user scope"
                        )
                    if option in ("--type", "-t") and value != "dir":
                        raise ValueError(
                            "Locked installation uses the project directory"
                        )
                    normalized.extend([option, value])
                    index += 2
                else:
                    if not option.startswith("-"):
                        paths.append(option)
                        normalized.append(str(root))
                    else:
                        normalized.append(option)
                    index += 1
            if selected_name is not None and selected_name != data["project"]["name"]:
                raise ValueError("The package name differs from the lock")
            if any(Path(arg).resolve() != root for arg in paths):
                raise ValueError(
                    "Locked sessions install the current project; update the lock to add dependencies"
                )
            args = [*args[:2], *normalized]
            if selected_name is None:
                args = [*args[:2], "--name", data["project"]["name"], *args[2:]]
            if not paths:
                args = [*args, str(root)]
    command = [native(tool), *args] if tool else args
    os.execvpe(str(command[0]), [str(value) for value in command], env)
