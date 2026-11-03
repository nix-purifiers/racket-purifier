"""Native explicit Git pinning, updates, extra inputs, and SDK-only graphs."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

repo = Path(__file__).resolve().parent.parent
subprocess.run(["nix", "build", ".", "--out-link", "sdk"], cwd=repo, check=True)
sdk = (repo / "sdk").resolve()
env = os.environ.copy()
env["PATH"] = str(sdk / "bin") + ":" + env["PATH"]


def command(root, *args):
    subprocess.run(
        [str(sdk / "bin/racket-purifier"), "--project", str(root), *args],
        check=True,
        env=env,
    )


with tempfile.TemporaryDirectory(prefix="racket-native-capture-") as temp:
    root = Path(temp) / "project"
    shutil.copytree(
        repo / "examples/minimal",
        root,
        ignore=shutil.ignore_patterns("compiled", ".racket-purifier"),
    )
    info = root / "info.rkt"
    original = info.read_text()
    old = "b1c74828b3e9d6676bedb52cb63a38ae3bf4506a"
    uri = "git://github.com/lexi-lambda/threading?path=threading-lib#" + old
    info.write_text(original.replace('"threading-lib"', json.dumps(uri)))
    command(root, "lock", "--update")
    companion = root / "racket-purifier.lock.json"
    pinned = json.loads(companion.read_text())
    assert (
        next(p["checksum"] for p in pinned["packages"] if p["name"] == "threading-lib")
        == old
    )
    command(root, "prefetch")
    subprocess.run(["raco", "test", "main.rkt"], cwd=root, env=env, check=True)
    info.write_text(original)
    (root / "version.txt").write_text("0.1.0\n")
    command(root, "lock", "--update", "--input", "version.txt")
    updated = json.loads(companion.read_text())
    assert (
        next(p["checksum"] for p in updated["packages"] if p["name"] == "threading-lib")
        != old
    )
    assert updated["extraInputs"] == ["version.txt"]
    command(root, "lock")
    command(root, "prefetch")
    info.write_text(
        '#lang info\n(define collection "purifier-example")\n(define version "0.1.0")\n(define deps \'("base"))\n'
    )
    command(root, "lock", "--update")
    empty = json.loads(companion.read_text())
    assert empty["packages"] == [] and empty["entries"] == []
    command(root, "prefetch")
    subprocess.run(
        ["racket", "-e", "(displayln (+ 20 22))"], cwd=root, env=env, check=True
    )
    missing = subprocess.run(
        ["racket", "-e", "(require threading)"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert missing.returncode != 0 and "collection not found" in missing.stderr, missing
print("Native Racket pin/update, explicit inputs, and empty graph passed")
