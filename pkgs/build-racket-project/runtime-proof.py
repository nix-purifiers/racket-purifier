"""Bind the shared CS runtime to unchanged original SDK artifacts."""
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sdk, output = map(Path, sys.argv[1:3])
readelf = sys.argv[3]
inputs = [sdk / "lib/libracketcs.a"]
inputs += sorted((sdk / "include/racket").glob("*.h"))
inputs += [sdk / "lib/racket" / name for name in ("petite.boot", "scheme.boot", "racket.boot")]
records = {}
for path in inputs:
    assert path.is_file() and path.resolve().is_relative_to(sdk.resolve()), "Foreign CS SDK artifact"
    records[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
library = output / "lib/libracketcs.so"
handle = ctypes.CDLL(str(library))
for symbol in ("racket_boot", "racket_apply", "racket_dynamic_require", "Slock_object"):
    getattr(handle, symbol)
dynamic = subprocess.check_output([readelf, "-d", str(library)], text=True)
assert "(SONAME)" not in dynamic, "CS runtime must retain its exact immutable link identity"
(output / "nix-support/original-sdk.json").write_text(json.dumps({
    "sdk": str(sdk), "originalFiles": records,
    "library": str(library), "librarySha256": hashlib.sha256(library.read_bytes()).hexdigest(),
    "dynamicSection": dynamic
}, sort_keys=True, indent=2) + "\n")
