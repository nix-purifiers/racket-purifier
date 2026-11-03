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
  makeWrapper,
}:
{
  src,
  lockFile ? src + "/racket-purifier.lock.json",
  fetchers ? { },
  nativeBuildInputs ? [ ],
  doCheck ? true,
  buildCommand ? "raco setup --avoid-main --no-docs --jobs 1 --pkgs \"$RACKET_PROJECT_NAME\"",
  checkCommand ? "raco test -p \"$RACKET_PROJECT_NAME\"",
  installCommand ? "",
  srcFilter ?
    path: type:
    !(builtins.elem (baseNameOf path) [
      ".git"
      ".racket-purifier"
      "compiled"
      "result"
      "__pycache__"
    ]),
}:
let
  lock = purifier.checkLock (import ./read-lock.nix { inherit lib; } { inherit src lockFile; });
  environment = import ./environment.nix {
    inherit
      lib
      runCommand
      fetchgit
      python3
      writeText
      purifier
      nativeRacket
      toolchain
      gcc
      sdkVersion
      findutils
      coreutils
      ;
  } { inherit lock fetchers nativeBuildInputs; };
  source = lib.cleanSourceWith {
    inherit src;
    filter = srcFilter;
  };
  manifest = writeText "racket-project-capture.json" (builtins.toJSON lock.data);
  project =
    runCommand "purified-racket-project"
      {
        nativeBuildInputs = [
          toolchain
          makeWrapper
        ]
        ++ nativeBuildInputs;
      }
      ''
        export PATH=${toolchain}/bin:$PATH HOME="$TMPDIR/home" PLTUSERHOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/cache" XDG_CONFIG_HOME="$TMPDIR/config"
        mkdir -p "$HOME" "$out/source" "$out/addon" "$out/bin"
        cp -pr ${source}/. "$out/source/"
        chmod -R u+w "$out/source"
        export PLTCONFIGDIR=${environment}/config PLTADDONDIR="$out/addon"
        export RACKET_PROJECT_NAME=${lib.escapeShellArg lock.data.project.name}
        racket ${../racket_purifier/project.rkt} link ${manifest} "$out/source"
        cd "$out/source"
        ${buildCommand}
        ${lib.optionalString doCheck checkCommand}
        ${installCommand}
        for tool in racket raco; do
          makeWrapper ${nativeRacket}/bin/$tool "$out/bin/$tool" \
            --set PLTCONFIGDIR ${environment}/config --set PLTADDONDIR "$out/addon" \
            --unset PLTCOLLECTS --unset PLTCOMPILEDROOTS
        done
      '';
  release =
    runCommand "racket-project-release"
      {
        nativeBuildInputs = [
          toolchain
          findutils
          coreutils
        ];
      }
      ''
        export HOME="$TMPDIR/home" PLTUSERHOME="$TMPDIR/home"
        mkdir -p "$HOME" "$out" source
        cp -pr ${source}/. source/
        chmod -R u+w source
        cp ${lockFile} source/racket-purifier.lock.json
        find source -type f -exec touch -h -d @1 {} +
        racket ${../racket_purifier/project.rkt} release ${manifest} "$PWD/source" "$out"
      '';
in
assert lock.problems == [ ];
assert lib.assertMsg (
  lock.data.toolVersions == {
    sdk = sdkVersion;
    racket = nativeRacket.version;
    gcc = gcc.version;
  }
) "Racket SDK changed; run racket-purifier lock --update";
{
  packages = {
    default = project;
    inherit project environment;
  };
  tests = project;
  inherit release;
  fetches = lock.entries;
}
