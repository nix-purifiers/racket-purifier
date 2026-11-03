"""SDK identity and project metadata freshness."""

import hashlib
import json
import os
from pathlib import Path
import subprocess

LOCK = "racket-purifier.lock.json"
STATE = Path("compiled") / "racket-purifier"
HERE = Path(__file__).resolve().parent.parent


def run(args, **kwargs):
    return subprocess.run([str(value) for value in args], check=True, **kwargs)


def native(tool):
    return os.environ["RACKET_PURIFIER_NATIVE_" + tool.upper()]


def versions():
    return {
        key.lower(): os.environ["RACKET_PURIFIER_" + key + "_VERSION"]
        for key in ("SDK", "RACKET", "GCC")
    }


def clean_env(state):
    env = os.environ.copy()
    for key in (
        "PLTCONFIGDIR",
        "PLTADDONDIR",
        "PLTUSERHOME",
        "PLTCOLLECTS",
        "PLTCOMPILEDROOTS",
        "PLT_COMPILED_FILE_CHECK",
        "RACKET_PURIFIER_PROJECT",
        "RACKET_PURIFIER_LOCK",
    ):
        env.pop(key, None)
    for key, leaf in (
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
    ):
        path = state / leaf
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env["PLTUSERHOME"] = env["HOME"]
    return env


def inputs(root, extra=()):
    names = sorted(set(["info.rkt", *extra]))
    result = {}
    for name in names:
        path = root / name
        if (
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or path.resolve() != path
            or not path.is_file()
        ):
            raise ValueError("Inputs must be regular files inside the project: " + name)
        blob = path.read_bytes()
        result[name] = {
            "content": blob.decode(),
            "sha256": hashlib.sha256(blob).hexdigest(),
        }
    return result


def load(root, companion):
    data = json.loads(companion.read_text())
    if data.get("version") != 1 or data.get("purifier") != "racket":
        raise ValueError("Invalid racket-purifier lock")
    if data.get("toolVersions") != versions():
        raise ValueError("Racket SDK changed; run racket-purifier lock --update")
    if data["inputs"] != inputs(root, data.get("extraInputs", [])):
        raise ValueError("Racket metadata changed; run racket-purifier lock --update")
    return data


def locate():
    selected = os.environ.get("RACKET_PURIFIER_LOCK")
    if selected:
        companion = Path(selected).resolve()
        root = Path(
            os.environ.get("RACKET_PURIFIER_PROJECT", companion.parent)
        ).resolve()
        return root, companion
    root = next(
        (path for path in (Path.cwd(), *Path.cwd().parents) if (path / LOCK).exists()),
        Path.cwd(),
    )
    return root, root / LOCK
