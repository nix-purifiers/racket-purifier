{
  lib,
  runCommand,
  nativeRacket,
  gcc,
  python3,
  binutils,
}:
let
  # Preserve the SDK's actual inputs, including its zlib-ng and libiconv choices.
  runtimeInputs = map (package: package.lib or package.out) nativeRacket.buildInputs;
in
runCommand "racket-cs-shared-runtime"
  {
    nativeBuildInputs = [
      gcc
      python3
      binutils
    ];
  }
  ''
    export SOURCE_DATE_EPOCH=1
    mkdir -p "$out/lib" "$out/nix-support"
    ${gcc}/bin/gcc -shared \
      -Wl,--whole-archive ${nativeRacket}/lib/libracketcs.a -Wl,--no-whole-archive \
      ${
        lib.concatMapStringsSep " " (package: "-L${package}/lib -Wl,-rpath,${package}/lib") runtimeInputs
      } \
      -lz -llz4 -lncursesw -liconv -lm -ldl -lpthread \
      -o "$out/lib/libracketcs.so"
    # No generic SONAME: consumers bind this exact immutable runtime path.
    python3 ${./runtime-proof.py} ${nativeRacket} "$out" ${binutils}/bin/readelf
  ''
