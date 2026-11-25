"""Native Racket binding, compiled-source, ABI and ownership controls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[1]
override = []
if source := os.environ.get("RACKET_TEST_CORE_SOURCE"):
    override = ["--override-input", "purifier", "path:" + source, "--no-write-lock-file"]
system = subprocess.check_output(["nix", "eval", "--impure", "--raw", "--expr", "builtins.currentSystem"], text=True).strip()
attribute = ".#checks." + system + ".native"
subprocess.run(["nix", "build", attribute, "--no-link", *override], cwd=repo, check=True)
producer = Path(subprocess.check_output(["nix", "eval", attribute + ".producer.outPath", "--raw", *override], cwd=repo, text=True).strip())
proof = json.loads((producer / "nix-support/racket-native/verified-libraries.json").read_text())
tools = proof["nativeTools"]
sdk = Path(proof["runtime"]["sdk"])
environment = Path(proof["config"]["path"]).parent.parent
cases = {
    "missing-binding": "name is not provided",
    "nonprocedure-binding": "Selected native Racket binding is not a procedure",
    "stale-compiled-source": "Native compiled-module source digest mismatch",
    "foreign-import": "Foreign resolved Racket module owner",
    "header-export": "Authored embedding header/export mismatch",
    "missing-export": "Missing callable embedding export",
    "foreign-header": "Foreign authored embedding input",
    "copied-runtime": "Foreign shared CS runtime owner",
}
for case, diagnostic in cases.items():
    with tempfile.TemporaryDirectory(prefix="racket-native-control-") as temporary:
        root = Path(temporary)
        project, original = root / "project", root / "original"
        shutil.copytree(producer, project, symlinks=True)
        for path in [project, *project.rglob("*")]:
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | 0o200)
        shutil.rmtree(project / "nix-support/racket-native")
        shutil.rmtree(project / "lib")
        shutil.rmtree(project / "include")
        shutil.copytree(repo / "tests/fixtures/native", original)
        specifications = {name: value["specification"] for name, value in proof["libraries"].items()}
        specifications = json.loads(json.dumps(specifications))
        first = specifications["first"]
        runtime = Path(proof["runtimeProducer"])
        env = dict(os.environ, PLTCONFIGDIR=str(environment / "config"), PLTADDONDIR=str(project / "addon"),
                   PATH=str(Path(tools["cc"]).parent) + os.pathsep + os.environ["PATH"])
        env.pop("PLTCOLLECTS", None)
        env.pop("PLTCOMPILEDROOTS", None)
        if case == "missing-binding":
            first["bindings"] = ["missing-native-binding"]
        elif case == "nonprocedure-binding":
            first["bindings"] = ["constant"]
            for folder in (original, project / "source"):
                with (folder / first["module"]).open("a") as stream:
                    stream.write("\n(provide constant)\n(define constant 42)\n")
        elif case == "stale-compiled-source":
            module = project / "source" / first["module"]
            source_bytes = module.read_bytes()
            module.write_text(module.read_text().replace("64 41", "64 99"))
            subprocess.run([str(sdk / "bin/raco"), "make", str(module)], env=env, check=True)
            module.write_bytes(source_bytes)
            os.utime(module, (1, 1))
        elif case == "foreign-import":
            (root / "foreign.rkt").write_text("#lang racket/base\n(provide foreign-value)\n(define foreign-value 1)\n")
            for folder in (original, project / "source"):
                module = folder / first["module"]
                module.write_text(module.read_text() + '\n(require "../../foreign.rkt")\n')
        elif case in ("header-export", "missing-export"):
            for folder in (original, project / "source"):
                header = folder / first["header"]
                text = header.read_text()
                if case == "header-export":
                    text = text.replace("uint32_t first_answer(uint32_t);\n", "")
                else:
                    text += "void missing_native_export(void);\n"
                header.write_text(text)
            if case == "missing-export":
                first["exports"].append("missing_native_export")
        elif case == "foreign-header":
            foreign = root / "foreign.h"
            foreign.write_bytes((project / "source" / first["header"]).read_bytes())
            (project / "source" / first["header"]).unlink()
            (project / "source" / first["header"]).symlink_to(foreign)
        else:
            copied = root / "copied-runtime"
            shutil.copytree(runtime, copied, symlinks=True)
            runtime = copied
        specs = root / "specifications.json"
        specs.write_text(json.dumps(specifications))
        command = [sys.executable, str(repo / "pkgs/build-racket-project/native-products.py"),
                   str(project), str(original), str(environment), str(sdk), str(runtime),
                   tools["cc"], tools["nm"], system, str(specs), tools["inspector"]]
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        assert result.returncode != 0 and diagnostic in result.stderr, (case, result.returncode, result.stdout, result.stderr)
        print(json.dumps({"case": case, "nativeExit": result.returncode, "diagnostic": diagnostic}), flush=True)
