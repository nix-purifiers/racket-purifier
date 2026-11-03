"""Reject malformed or stale captures at evaluation without IFD."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile

repo = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix="racket-evaluation-") as temp:
    root = Path(temp) / "project"
    shutil.copytree(repo / "examples/minimal", root)
    lock = root / "racket-purifier.lock.json"
    original = lock.read_text()
    expression = (
        f"let flake = builtins.getFlake {json.dumps('path:' + str(repo))}; "
        f"in (flake.lib.racket-purifier.readLock {{ src = /. + {json.dumps(str(root))}; }}).problems"
    )

    def problems():
        result = subprocess.run(
            [
                "nix",
                "eval",
                "--impure",
                "--option",
                "allow-import-from-derivation",
                "false",
                "--json",
                "--expr",
                expression,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    assert problems() == []
    for change in (
        lambda d: d.update(version=99),
        lambda d: d["entries"][0].update(path="../escape"),
        lambda d: d["entries"][0].update(hash="unhashed"),
        lambda d: d["inputs"]["info.rkt"].update(content="changed"),
        lambda d: d["packages"][0].update(checksum="unverified"),
        lambda d: d["packages"][0].update(subpath="../outside"),
        lambda d: d["project"].update(name="../outside"),
    ):
        data = json.loads(original)
        change(data)
        lock.write_text(json.dumps(data))
        assert problems()
    lock.write_text(original)
    (root / "info.rkt").write_text((root / "info.rkt").read_text() + "\n")
    assert problems()
    lock.unlink()
    assert problems()
print("Racket evaluation checks passed without IFD")
