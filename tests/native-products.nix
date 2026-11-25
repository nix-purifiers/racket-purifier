{
  pkgs,
  src ? ./fixtures/native,
  expected ? 41,
}:
let
  built = pkgs.racket-purifier.buildRacketProject {
    inherit src;
    nativeLibraries = {
      first = {
        bridge = "bridge.c";
        header = "native-answer.h";
        module = "first.rkt";
        bindings = [ "answer" ];
        initialize = "first_init";
        exports = [
          "first_init"
          "first_answer"
        ];
      };
      second = {
        bridge = "bridge.c";
        header = "native-answer.h";
        module = "second.rkt";
        bindings = [ "answer" ];
        initialize = "second_bind";
        exports = [
          "second_bind"
          "second_answer"
        ];
        defines = [ "SECOND_BRIDGE" ];
      };
    };
  };
  producer = built.packages.project;
  projection = built.projections.native;
  python = pkgs.python3.withPackages (p: [ p.cffi ]);
in
pkgs.runCommand "racket-native-embedding-consumers"
  {
    nativeBuildInputs = [
      python
      pkgs.gcc
      pkgs.jdk21
    ];
    passthru = { inherit built producer projection; };
  }
  ''
    mkdir "$out"
    cc ${./native-consumer.c} -DEXPECTED=${toString expected} \
      -I${producer}/include/first ${producer}/lib/libfirst.so ${producer}/lib/libsecond.so -o consume
    ./consume
    python ${./native-consumers.py} ${projection} ${toString expected} ${producer}/nix-support/racket-native/verified-libraries.json
    cp ${./NativeAnswer.java} NativeAnswer.java
    javac --enable-preview --release 21 NativeAnswer.java
    java @${built.projections.java-ffi}/java.args --enable-preview --enable-native-access=ALL-UNNAMED NativeAnswer ${toString expected}
    cp ${producer}/nix-support/racket-native/verified-libraries.json "$out/"
  ''
