{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  nix,
  gh,
  toolchain,
  nativeRacket,
  gcc,
  cacert,
  sdkVersion,
  nixpkgsSrc,
  purifierSrc,
}:
stdenvNoCC.mkDerivation {
  pname = "racket-purifier";
  version = "0.1.0";
  src = ../..;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/racket-purifier"
    cp -r racket_purifier nix lib-overlays pkgs "$out/lib/racket-purifier/"
    install -m755 bin/racket-purifier "$out/bin/racket-purifier"
    substituteInPlace "$out/lib/racket-purifier/nix/realize.nix" \
      --replace-fail '@nixpkgs@' '${nixpkgsSrc}' \
      --replace-fail '@purifier@' '${purifierSrc}'
    wrapProgram "$out/bin/racket-purifier" \
      --prefix PATH : ${
        lib.makeBinPath [
          python3
          nix
          gh
          toolchain
        ]
      } \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set RACKET_PURIFIER_NATIVE_RACKET ${nativeRacket}/bin/racket \
      --set RACKET_PURIFIER_NATIVE_RACO ${nativeRacket}/bin/raco \
      --set RACKET_PURIFIER_COLLECTS ${nativeRacket}/share/racket/collects \
      --set RACKET_PURIFIER_SDK_VERSION ${sdkVersion} \
      --set RACKET_PURIFIER_RACKET_VERSION ${nativeRacket.version} \
      --set RACKET_PURIFIER_GCC_VERSION ${gcc.version} \
      --set RACKET_PURIFIER_SDK "$out" \
      --set RACKET_PURIFIER_TOOLCHAIN ${toolchain}
    for tool in racket raco; do
      makeWrapper "$out/bin/racket-purifier" "$out/bin/$tool" --add-flags "--native --tool=$tool --"
    done
    for program in ${toolchain}/bin/*; do
      name=$(basename "$program")
      if [ ! -e "$out/bin/$name" ]; then ln -s "$program" "$out/bin/$name"; fi
    done
  '';
  meta = {
    description = "Native Racket workflow with locked Nix-resolved dependencies";
    homepage = "https://nix-purifiers.github.io/";
    license = lib.licenses.mit;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
    mainProgram = "racket-purifier";
  };
}
