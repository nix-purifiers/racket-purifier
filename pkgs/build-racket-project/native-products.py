"""Compile authored ABI bridges against one original CS runtime producer."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


project, original, environment, sdk, runtime = map(Path, sys.argv[1:6])
cc, nm, system, specifications, inspector = sys.argv[6:]
project, original, environment, sdk, runtime = [path.resolve(strict=True)
                                               for path in (project, original, environment, sdk, runtime)]
source = project / "source"
runtime_library = runtime / "lib/libracketcs.so"
sdk_proof = json.loads((runtime / "nix-support/original-sdk.json").read_text())
assert Path(sdk_proof["sdk"]).resolve() == sdk, "Foreign CS runtime SDK"
assert sha(runtime_library) == sdk_proof["librarySha256"], "CS runtime library changed"
for name, expected in sdk_proof["originalFiles"].items():
    assert sha(Path(name)) == expected, "Original CS SDK artifact changed"
support = project / "nix-support/racket-native"
support.mkdir(parents=True)
records = {}
for name, spec in json.loads(Path(specifications).read_text()).items():
    selected = {}
    for key in ("bridge", "header", "module"):
        path = (source / spec[key]).resolve(strict=True)
        before = (original / spec[key]).resolve(strict=True)
        assert path.is_relative_to(source) and before.is_relative_to(original), "Foreign authored embedding input"
        assert path.is_file() and before.is_file() and path.read_bytes() == before.read_bytes(), "Authored embedding input changed"
        selected[key] = path
    bindings_file = support / (name + "-bindings.json")
    bindings_file.write_text(json.dumps(spec["bindings"]))
    graph_raw = subprocess.check_output([str(sdk / "bin/racket"), inspector,
                                         str(selected["module"]), str(bindings_file)], text=True)
    graph = json.loads(graph_raw)
    owners = {}
    for filename in graph["files"]:
        path = Path(filename).resolve(strict=True)
        if path.is_relative_to(source):
            origin, relative = "project", str(path.relative_to(source))
        elif path.is_relative_to(environment):
            origin, relative = "dependency", str(path.relative_to(environment))
        elif path.is_relative_to(sdk):
            origin, relative = "sdk", str(path.relative_to(sdk))
        else:
            raise AssertionError("Foreign resolved Racket module owner: " + str(path))
        owners[str(path)] = {"origin": origin, "relative": relative, "sha256": sha(path)}
    assert str(selected["module"]) in owners, "Native module graph omitted selected module"
    assert any(record["origin"] == "sdk" for record in owners.values()), "Missing original Racket module runtime"
    header_check = subprocess.run([cc, "-x", "c", "-fsyntax-only", "-include", str(selected["header"]), "-"],
                                  input="void *exports[] = {" + ",".join("(void*)&" + symbol for symbol in spec["exports"]) + "};\n",
                                  text=True, capture_output=True)
    assert header_check.returncode == 0, "Authored embedding header/export mismatch: " + header_check.stderr
    library = project / "lib" / ("lib" + name + ".so")
    library.parent.mkdir(exist_ok=True)
    definitions = {
        "RACKET_SDK": str(sdk), "RACKET_CONFIG_DIR": str(environment / "config"),
        "RACKET_ADDON_DIR": str(project / "addon"), "RACKET_MODULE": str(selected["module"])
    }
    command = [cc, "-shared", "-fPIC", "-I" + str(sdk / "include/racket"),
               *["-D" + key + "=" + json.dumps(value) for key, value in definitions.items()],
               *["-D" + define for define in spec.get("defines", [])],
               str(selected["bridge"]), str(runtime_library), "-o", str(library)]
    subprocess.run(command, check=True)
    elf = library.read_bytes()
    endian = "<" if elf[5] == 1 else ">"
    assert elf[:5] == b"\x7fELF\x02" and struct.unpack_from(endian + "H", elf, 16)[0] == 3, "Expected native shared embedding library"
    assert struct.unpack_from(endian + "H", elf, 18)[0] == {"x86_64-linux": 62, "aarch64-linux": 183}[system], "Foreign embedding architecture"
    symbols = subprocess.check_output([nm, "-D", "--defined-only", str(library)], text=True)
    callable_symbols = {parts[-1] for line in symbols.splitlines()
                        if len(parts := line.split()) >= 3 and parts[-2] in ("T", "W")}
    assert set(spec["exports"]).issubset(callable_symbols), "Missing callable embedding export"
    dynamic = subprocess.check_output([str(Path(nm).parent / "readelf"), "-d", str(library)], text=True)
    assert str(runtime_library) in dynamic, "Embedding did not bind its exact shared CS runtime"
    installed_header = project / "include" / name / selected["header"].name
    installed_header.parent.mkdir(parents=True)
    shutil.copy2(selected["header"], installed_header)
    for path, record in owners.items():
        assert sha(Path(path)) == record["sha256"], "Resolved Racket source changed during embedding build"
    records[name] = {"specification": spec, "command": command, "moduleGraph": graph,
                     "moduleOwners": owners, "library": str(library), "librarySha256": sha(library),
                     "header": str(installed_header), "headerSha256": sha(installed_header),
                     "dynamicSymbols": symbols, "dynamicSection": dynamic}
authored = {str(path.relative_to(original)): sha(path)
            for path in sorted(original.rglob("*")) if path.is_file()}
after = {relative: sha(source / relative) if (source / relative).is_file() else None for relative in authored}
(support / "verified-libraries.json").write_text(json.dumps({
    "libraries": records, "runtime": sdk_proof, "runtimeProducer": str(runtime),
    "authoredInputs": authored, "postBuildInputs": after,
    "config": {"path": str(environment / "config/config.rktd"), "sha256": sha(environment / "config/config.rktd")}
}, sort_keys=True, indent=2) + "\n")
