{
  lib,
  runCommand,
  fetchgit,
  python3,
  writeText,
  purifier,
  nativeRacket,
  toolchain,
  gcc,
  sdkVersion,
  findutils,
  coreutils,
}:
{
  lock,
  fetchers ? { },
  nativeBuildInputs ? [ ],
}:
let
  checked = purifier.checkLock lock;
  sources = purifier.tree (
    {
      name = "locked-racket-sources";
      entries = checked.entries;
      inherit
        runCommand
        fetchgit
        python3
        writeText
        ;
    }
    // fetchers
  );
  manifest = writeText "racket-capture.json" (builtins.toJSON checked.data);
  names = lib.escapeShellArgs (map (p: p.name) checked.data.packages);
in
assert checked.problems == [ ];
assert lib.assertMsg (
  checked.data.toolVersions == {
    sdk = sdkVersion;
    racket = nativeRacket.version;
    gcc = gcc.version;
  }
) "Racket SDK changed; run racket-purifier lock --update";
runCommand "purified-racket-environment"
  {
    nativeBuildInputs = [
      toolchain
      findutils
      coreutils
    ]
    ++ nativeBuildInputs;
  }
  ''
    export PATH=${toolchain}/bin:$PATH HOME="$TMPDIR/home" PLTUSERHOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/cache" XDG_CONFIG_HOME="$TMPDIR/config"
    mkdir -p "$HOME" "$out/addon"
    racket -A "$out/addon" ${../../racket_purifier/install.rkt} ${manifest} ${sources}
    racket -A "$out/addon" ${../../racket_purifier/check-installed.rkt} ${manifest}
    find "$out/addon" -type f -exec touch -h -d @1 {} +
    ${lib.optionalString (checked.data.packages != [ ]) ''
      racket -A "$out/addon" -N raco -l- raco/main setup --avoid-main --no-docs --jobs 1 --pkgs ${names}
    ''}
    racket ${../../racket_purifier/config.rkt} ${nativeRacket}/etc/racket/config.rktd "$out" "$out/config"
    cp ${manifest} "$out/capture.json"
    ln -s ${sources} "$out/sources"
  ''
