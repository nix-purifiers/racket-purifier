"""Installed wrappers, native package consumers, bytecode and definition lookup."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

repo = Path(__file__).resolve().parent.parent


def run(args, **kwargs):
    result = subprocess.run([str(value) for value in args], **kwargs)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout[-12000:])
        if result.stderr:
            print(result.stderr[-12000:])
        result.check_returncode()
    return result


run(["nix", "build", ".", "--out-link", "sdk"], cwd=repo)
sdk = (repo / "sdk").resolve()
with tempfile.TemporaryDirectory(prefix="racket-conformance-") as temp:
    temp = Path(temp)
    root = temp / "project"
    shutil.copytree(
        repo / "examples/minimal",
        root,
        ignore=shutil.ignore_patterns(".racket-purifier", "compiled"),
    )
    data = json.loads((root / "racket-purifier.lock.json").read_text())
    name = data["project"]["name"]
    env = os.environ.copy()
    env["PATH"] = str(sdk / "bin") + ":" + env["PATH"]
    poison = temp / "poison"
    poison.mkdir()
    (poison / "config.rktd").write_text("invalid configuration")
    env.update(
        {
            "PLTCONFIGDIR": str(poison),
            "PLTCOLLECTS": str(poison),
            "PLTADDONDIR": str(poison),
            "PLTUSERHOME": str(poison),
        }
    )
    run(["racket-purifier", "prefetch"], cwd=root, env=env)
    run(["raco", "pkg", "install", "--no-docs", "."], cwd=root, env=env)
    run(["raco", "make", "main.rkt"], cwd=root, env=env)
    test = ["raco", "test", "--process", "-p", name]
    tested = run(test, cwd=root, env=env, capture_output=True, text=True)
    assert "1 test passed" in tested.stdout, tested
    active_result = run(
        ["racket-purifier", "exec", "--", "env"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    active = dict(
        line.split("=", 1) for line in active_result.stdout.splitlines() if "=" in line
    )
    environment = Path(active["PLTCONFIGDIR"]).parent
    assert str(environment).startswith("/nix/store/")
    profile = (root / "compiled/racket-purifier/environment.json").resolve()
    references = run(
        ["nix-store", "--query", "--references", profile],
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert str(environment) in references and str(sdk) in references, references
    assert (root / "compiled/main_rkt.zo").is_file()
    assert list((environment / "addon").rglob("*.zo"))
    assert not list((root / "compiled/racket-purifier/session").rglob("*.zo"))
    traced = run(
        [
            "racket",
            "-e",
            "(define previous (current-load))",
            "-e",
            '(current-load (lambda (path expected) (eprintf "LOAD\\t~a\\n" path) (previous path expected)))',
            "-e",
            "(dynamic-require (quote threading) #f)",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert str(environment) in traced.stderr and ".zo" in traced.stderr, traced
    assert not any(
        line.endswith(".rkt")
        for line in traced.stderr.splitlines()
        if line.startswith("LOAD")
    ), traced.stderr
    definition = run(
        [
            "racket",
            "-e",
            "(require threading syntax/modresolve)",
            "-e",
            "(displayln (resolve-module-path-index (car (identifier-binding (quote-syntax ~>))) #f))",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert definition.stdout.startswith(
        str(environment)
    ) and definition.stdout.strip().endswith(".rkt"), definition
    app = root / "main.rkt"
    original = app.read_text()
    app.write_text(original.replace("~> 40", "~> 41"))
    (root / "compiled/main_rkt.zo").unlink(missing_ok=True)
    failed = subprocess.run(
        ["raco", "test", "--make", "main.rkt"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert failed.returncode != 0 and "FAILURE" in failed.stderr, failed
    app.write_text(original)
    (root / "compiled/main_rkt.zo").unlink(missing_ok=True)
    run(["raco", "test", "--make", "main.rkt"], cwd=root, env=env)
    companion = root / "racket-purifier.lock.json"
    before = companion.read_bytes()
    run(["racket-purifier", "lock"], cwd=root, env=env)
    assert companion.read_bytes() == before
    external = temp / "external.json"
    companion.rename(external)
    selected = env | {
        "RACKET_PURIFIER_PROJECT": str(root),
        "RACKET_PURIFIER_LOCK": str(external),
    }
    run(["racket-purifier", "exec", "--", *test], cwd=root, env=selected)
    assert not companion.exists()
    external.rename(companion)
    info = root / "info.rkt"
    original_info = info.read_text()
    info.write_text(original_info + "\n")
    stale = subprocess.run(
        ["racket", "main.rkt"], cwd=root, env=env, capture_output=True, text=True
    )
    assert stale.returncode != 0 and "metadata changed" in stale.stderr, stale
    info.write_text(original_info)
    release = run(
        ["racket-purifier", "release"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    output = Path(release.stdout.strip())
    archive = output / (name + ".zip")
    checksum = output / (name + ".zip.CHECKSUM")
    assert (
        hashlib.sha1(archive.read_bytes()).hexdigest() == checksum.read_text().strip()
    )
    consumer = temp / "consumer"
    consumer.mkdir()
    consumer_addon = consumer / "addon"
    consumer_addon.mkdir()
    ordinary = active | {
        "PLTADDONDIR": str(consumer_addon),
        "PLTUSERHOME": str(consumer / "home"),
        "HOME": str(consumer / "home"),
    }
    (consumer / "home").mkdir()
    run(
        [active["RACKET_PURIFIER_NATIVE_RACO"], "pkg", "install", "--no-docs", archive],
        cwd=consumer,
        env=ordinary,
    )
    consumed = run(
        [active["RACKET_PURIFIER_NATIVE_RACO"], "test", "--process", "-p", name],
        cwd=consumer,
        env=ordinary,
        capture_output=True,
        text=True,
    )
    assert "1 test passed" in consumed.stdout, consumed
    located = run(
        [
            active["RACKET_PURIFIER_NATIVE_RACKET"],
            "-e",
            '(displayln (collection-file-path "main.rkt" "purifier-example"))',
        ],
        cwd=consumer,
        env=ordinary,
        capture_output=True,
        text=True,
    )
    assert located.stdout.startswith(str(consumer_addon)), located
    fake = temp / "gh"
    fake.write_text(
        "#!/usr/bin/env python3\nimport os,pathlib,shutil,sys\n"
        "if sys.argv[1:3]==['release','view']:sys.exit(int(os.environ['FAKE_VIEW']))\n"
        "for a in sys.argv[3:]:\n p=pathlib.Path(a)\n if p.is_file():shutil.copyfile(p,pathlib.Path(os.environ['FAKE_DEST'])/p.name)\n"
    )
    fake.chmod(0o755)
    for exists in (False, True):
        uploaded = temp / ("upload" if exists else "create")
        uploaded.mkdir()
        run(
            ["racket-purifier", "publish", "--repo", "fixture/project", "--tag", "v1"],
            cwd=root,
            env=env
            | {
                "RACKET_PURIFIER_GH": str(fake),
                "FAKE_VIEW": "0" if exists else "1",
                "FAKE_DEST": str(uploaded),
            },
        )
        for artifact in (archive, checksum):
            assert (uploaded / artifact.name).read_bytes() == artifact.read_bytes()
    unlocked = temp / "unlocked"
    unlocked.mkdir()
    fallback_env = os.environ.copy()
    for key in (
        "PLTCONFIGDIR",
        "PLTADDONDIR",
        "PLTUSERHOME",
        "PLTCOLLECTS",
        "RACKET_PURIFIER_LOCK",
        "RACKET_PURIFIER_PROJECT",
    ):
        fallback_env.pop(key, None)
    fallback_env.update(
        {"PATH": env["PATH"], "HOME": str(unlocked), "PLTUSERHOME": str(unlocked)}
    )
    for tool, args in (
        ("raco", ["help"]),
        (
            "racket",
            [
                "-e",
                "(displayln (read-line))",
                "-e",
                '(eprintf "native stderr\\n")',
                "-e",
                "(exit 7)",
            ],
        ),
    ):
        baseline = subprocess.run(
            [active["RACKET_PURIFIER_NATIVE_" + tool.upper()], *args],
            cwd=unlocked,
            env=fallback_env,
            input=b"stdin survives\n",
            capture_output=True,
        )
        wrapped = subprocess.run(
            [tool, *args],
            cwd=unlocked,
            env=fallback_env,
            input=b"stdin survives\n",
            capture_output=True,
        )
        assert wrapped.returncode == baseline.returncode
        assert wrapped.stdout == baseline.stdout
        assert (
            wrapped.stderr
            == b"warning: no racket-purifier lockfile; using ordinary impure resolution\n"
            + baseline.stderr
        )
print("Racket host conformance passed")
