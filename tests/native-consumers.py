import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

projection, expected = Path(sys.argv[1]), int(sys.argv[2])
proof = json.loads(Path(sys.argv[3]).read_text())
sys.path.insert(0, str(projection))
import purifier_native

handles = [purifier_native.load(name, mode=os.RTLD_NOW | os.RTLD_NODELETE) for name in ("first", "second")]
class DlInfo(ctypes.Structure):
    _fields_ = [("filename", ctypes.c_char_p), ("base", ctypes.c_void_p),
                ("symbol", ctypes.c_char_p), ("address", ctypes.c_void_p)]
dladdr = ctypes.CDLL(None).dladdr
dladdr.argtypes = [ctypes.c_void_p, ctypes.POINTER(DlInfo)]
dladdr.restype = ctypes.c_int
runtime = Path(proof["runtime"]["library"]).resolve()
for handle in handles:
    for name in ("racket_boot", "racket_apply", "Slock_object"):
        info = DlInfo()
        assert dladdr(ctypes.cast(getattr(handle, name), ctypes.c_void_p), ctypes.byref(info))
        assert Path(info.filename.decode()).resolve() == runtime
assert hashlib.sha256(runtime.read_bytes()).hexdigest() == proof["runtime"]["librarySha256"]
for handle, initializer in zip(handles, ("first_init", "second_bind")):
    function = getattr(handle, initializer)
    function.argtypes = []
    function.restype = ctypes.c_int
    assert function() == 0
for handle, name in zip(handles, ("first_answer", "second_answer")):
    function = getattr(handle, name)
    function.argtypes = [ctypes.c_uint32]
    function.restype = ctypes.c_uint32
for value in [*range(100), 0xffffffff]:
    assert handles[0].first_answer(value) == (value + expected) % (1 << 32)
    assert handles[1].second_answer(value) == (value + expected + 1) % (1 << 32)
libraries = json.loads((projection / "catalog.json").read_text())["libraries"]
program = '''from cffi import FFI
import os
from pathlib import Path
f=FFI(); f.cdef("int first_init(void); int second_bind(void); uint32_t first_answer(uint32_t); uint32_t second_answer(uint32_t);")
a=f.dlopen(LIBRARIES["first"],flags=os.RTLD_NOW|os.RTLD_NODELETE)
b=f.dlopen(LIBRARIES["second"],flags=os.RTLD_NOW|os.RTLD_NODELETE)
assert a.first_init()==0 and b.second_bind()==0
for value in [*range(100),0xffffffff]:
 assert a.first_answer(value)==(value+EXPECTED) % (1<<32)
 assert b.second_answer(value)==(value+EXPECTED+1) % (1<<32)
f.dlclose(b);f.dlclose(a)
maps=Path("/proc/self/maps").read_text()
for path in [*LIBRARIES.values(),RUNTIME]: assert str(Path(path).resolve()) in maps
print("Actual shared-CS Racket CFFI200/GC/overflow/close-maps PASS")
'''
subprocess.run([sys.executable, "-c", "LIBRARIES=" + repr(libraries) + "\nEXPECTED=" + str(expected)
                + "\nRUNTIME=" + repr(str(runtime)) + "\n" + program], check=True)
print("Actual shared-CS Racket ctypes200/GC/overflow/origins PASS")
