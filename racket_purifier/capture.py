"""Capture native Racket resolution and exact transport bytes."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import urllib.parse

from .common import HERE, clean_env, inputs, load, native, run, versions


def safe(name):
    if not re.fullmatch(r"[A-Za-z0-9_.+-]+", name) or name in (".", ".."):
        raise ValueError("Unsupported package name: " + name)
    return name


def sri(blob):
    return "sha256-" + base64.b64encode(hashlib.sha256(blob).digest()).decode()


def capture(root, companion, update=False, extra=(), package_name=None):
    previous = json.loads(companion.read_text()) if companion.exists() else None
    extra = list(extra or (previous or {}).get("extraInputs", []))
    if previous and not update:
        if extra != previous.get("extraInputs", []) or (
            package_name and package_name != previous["project"]["name"]
        ):
            raise ValueError("Lock options changed; run lock --update")
        load(root, companion)
        print("Retained " + str(companion))
        return
    captured_inputs = inputs(root, extra)
    if companion in [root / name for name in captured_inputs]:
        raise ValueError("Lock output must be distinct from project inputs")
    name = safe(
        package_name or (previous or {}).get("project", {}).get("name", root.name)
    )
    with tempfile.TemporaryDirectory(prefix="racket-purifier-") as temp:
        temp = Path(temp)
        project = temp / name
        shutil.copytree(
            root,
            project,
            ignore=shutil.ignore_patterns(
                ".git", ".racket-purifier", "compiled", "result*", "__pycache__"
            ),
        )
        env = clean_env(temp)
        env["PATH"] = os.environ["RACKET_PURIFIER_TOOLCHAIN"] + "/bin:" + env["PATH"]
        addon = temp / "addon"
        addon.mkdir()
        env["PLTADDONDIR"] = str(addon)
        run(
            [
                native("raco"),
                "pkg",
                "install",
                "--auto",
                "--no-setup",
                "--source",
                "--user",
                "--name",
                name,
                project,
            ],
            env=env,
            cwd=project,
        )
        result = run(
            [native("racket"), HERE / "racket_purifier/export.rkt", name, project],
            env=env,
            cwd=project,
            capture_output=True,
            text=True,
        )
        plan = json.loads(result.stdout)
        if not isinstance(plan["project"]["version"], str):
            raise ValueError("The native package version must be a string")
        if plan["vm"] != "chez-scheme":
            raise ValueError("This SDK integration requires Racket CS")
        entries = {}
        packages = []
        for record in plan["packages"]:
            safe(record["name"])
            checksum = record["checksum"]
            if not isinstance(checksum, str) or not re.fullmatch(
                r"[0-9a-f]{40}", checksum
            ):
                raise ValueError(
                    "A native package checksum is required: " + record["name"]
                )
            package = {
                key: record[key] for key in ("name", "source", "type", "checksum")
            }
            if record["type"] == "file-url":
                if not record["source"].startswith("https://"):
                    raise ValueError("Only HTTPS package archives are supported")
                downloaded = temp / (record["name"] + ".archive")
                run(
                    [
                        "curl",
                        "--fail",
                        "--location",
                        "--silent",
                        "--show-error",
                        "--output",
                        downloaded,
                        record["source"],
                    ],
                    env=env,
                )
                blob = downloaded.read_bytes()
                if hashlib.sha1(blob).hexdigest() != checksum:
                    raise ValueError(
                        "Archive changed after native resolution: " + record["name"]
                    )
                source_path = urllib.parse.urlsplit(record["source"]).path
                suffix = next(
                    (
                        value
                        for value in (".zip", ".tar.gz", ".tgz", ".plt")
                        if source_path.endswith(value)
                    ),
                    None,
                )
                if suffix is None:
                    raise ValueError("Unsupported archive extension: " + record["name"])
                path = "archives/" + record["name"] + suffix
                entries[path] = {
                    "path": path,
                    "url": record["source"],
                    "hash": sri(blob),
                    "mirrors": [],
                }
                package.update(entry=path, subpath="")
            elif record["type"] in ("git", "git-url", "github"):
                git = record["git"]
                prefetch = run(
                    [
                        "nix-prefetch-git",
                        "--quiet",
                        "--url",
                        git["url"],
                        "--rev",
                        checksum,
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                )
                fetched = json.loads(prefetch.stdout)
                if (
                    fetched["rev"] != checksum
                    or fetched["fetchSubmodules"]
                    or fetched["leaveDotGit"]
                ):
                    raise ValueError("Unexpected Git prefetch result")
                subpath = git["subpath"]
                if Path(subpath).is_absolute() or ".." in Path(subpath).parts:
                    raise ValueError("Git package path escapes its repository")
                candidate = Path(fetched["path"]) / subpath
                hashes = [
                    run(
                        ["nix", "hash", "path", path],
                        env=env,
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    for path in (candidate, record["directory"])
                ]
                if hashes[0] != hashes[1]:
                    raise ValueError(
                        "Native package source differs from the pinned Git subtree: "
                        + record["name"]
                    )
                key = hashlib.sha256((git["url"] + "#" + checksum).encode()).hexdigest()
                path = "git/" + key
                entries[path] = {
                    "path": path,
                    "hash": fetched["hash"],
                    "git": {
                        "url": git["url"],
                        "rev": checksum,
                        "submodules": False,
                        "leaveDotGit": False,
                        "commitObject": None,
                    },
                }
                package.update(entry=path, subpath=subpath)
            else:
                raise ValueError("Unsupported native package source: " + record["type"])
            packages.append(package)
        data = {
            "version": 1,
            "purifier": "racket",
            "toolVersions": versions(),
            "vm": plan["vm"],
            "project": plan["project"],
            "sdkPackages": plan["sdkPackages"],
            "inputs": captured_inputs,
            "extraInputs": extra,
            "packages": packages,
            "entries": sorted(entries.values(), key=lambda item: item["path"]),
        }
        companion.parent.mkdir(parents=True, exist_ok=True)
        pending = companion.with_name(companion.name + ".tmp")
        pending.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
        pending.replace(companion)
    print(f"Locked {len(packages)} native packages")
