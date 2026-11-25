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
  binutils,
  stdenv,
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
  nativeLibraries ? { },
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
  lock = purifier.checkLock (
    import ../../lib-overlays/default/read-lock.nix { inherit lib; } { inherit src lockFile; }
  );
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
  runtime = import ./native-runtime.nix {
    inherit
      lib
      runCommand
      nativeRacket
      gcc
      python3
      binutils
      ;
  };
  nativeSpecifications = writeText "racket-native-libraries.json" (builtins.toJSON nativeLibraries);
  relative =
    value:
    builtins.isString value
    && value != ""
    && !lib.hasPrefix "/" value
    && builtins.all (
      part:
      !(builtins.elem part [
        ""
        "."
        ".."
      ])
    ) (lib.splitString "/" value);
  symbol = value: builtins.isString value && builtins.match "[A-Za-z_][A-Za-z0-9_]*" value != null;
  validNative =
    name: spec:
    symbol name
    && builtins.isAttrs spec
    &&
      builtins.attrNames (
        removeAttrs spec [
          "bridge"
          "header"
          "module"
          "bindings"
          "exports"
          "initialize"
          "defines"
        ]
      ) == [ ]
    && relative (spec.bridge or null)
    && lib.hasSuffix ".c" spec.bridge
    && relative (spec.header or null)
    && relative (spec.module or null)
    && builtins.isList (spec.bindings or null)
    && spec.bindings != [ ]
    && lib.all (value: builtins.isString value && value != "") spec.bindings
    && builtins.isList (spec.exports or null)
    && spec.exports != [ ]
    && lib.all symbol spec.exports
    && symbol (spec.initialize or null)
    && builtins.elem spec.initialize spec.exports
    && builtins.isList (spec.defines or [ ])
    && lib.all symbol (spec.defines or [ ]);
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
        racket ${../../racket_purifier/project.rkt} link ${manifest} "$out/source"
        cd "$out/source"
        ${buildCommand}
        ${lib.optionalString doCheck checkCommand}
        ${installCommand}
        ${lib.optionalString (nativeLibraries != { }) ''
          ${python3}/bin/python3 ${./native-products.py} "$out" ${source} ${environment} ${nativeRacket} ${runtime} \
            ${gcc}/bin/gcc ${binutils}/bin/nm ${stdenv.hostPlatform.system} ${nativeSpecifications} ${./module-graph.rkt}
        ''}
        for tool in racket raco; do
          makeWrapper ${nativeRacket}/bin/$tool "$out/bin/$tool" \
            --set PLTCONFIGDIR ${environment}/config --set PLTADDONDIR "$out/addon" \
            --unset PLTCOLLECTS --unset PLTCOMPILEDROOTS
        done
      '';
  projections = lib.optionalAttrs (nativeLibraries != { }) (
    purifier.nativeProjections {
      producer = project;
      libraries = lib.mapAttrs (name: _: "lib/lib${name}.so") nativeLibraries;
      includeDirectories = lib.mapAttrsToList (name: _: "include/${name}") nativeLibraries;
      targetMetadata = lib.mapAttrs (_: spec: {
        abi = "c";
        inherit (spec)
          module
          bindings
          exports
          initialize
          ;
        runtimeProducer = toString runtime;
        toolVersions = lock.data.toolVersions;
        runtimeContract = "One initialized CS runtime; caller-owned GC roots; same native thread; process-lifetime load";
      }) nativeLibraries;
      system = stdenv.hostPlatform.system;
      inherit runCommand python3;
    }
  );
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
        racket ${../../racket_purifier/project.rkt} release ${manifest} "$PWD/source" "$out"
      '';
in
assert lib.assertMsg
  (lib.all (name: validNative name nativeLibraries.${name}) (builtins.attrNames nativeLibraries))
  "Racket native libraries require authored bridge/header/module, bindings, initializer and callable exports";
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
  inherit release projections;
  fetches = lock.entries;
}
