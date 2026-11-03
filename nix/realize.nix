{
  project,
  companion,
  target ? "environment",
  sdk ? null,
  profile ? false,
}:
let
  nixpkgsSrc = /. + "@nixpkgs@";
  pkgs = import nixpkgsSrc { };
  purifier = import (/. + "@purifier@/nix/lib") { inherit (pkgs) lib; };
  nativeRacket = pkgs.racket-minimal;
  toolchain = pkgs.callPackage ./toolchain.nix { inherit nativeRacket; };
  sdkVersion = import ./sdk-version.nix { inherit nixpkgsSrc; };
  args = {
    src = /. + project;
    lockFile = /. + companion;
  };
  lock = import ./read-lock.nix { inherit (pkgs) lib; } args;
  output =
    if target == "environment" then
      pkgs.callPackage ./environment.nix {
        inherit
          purifier
          nativeRacket
          toolchain
          sdkVersion
          ;
      } { inherit lock; }
    else if target == "release" then
      (pkgs.callPackage ./build-project.nix {
        inherit
          purifier
          nativeRacket
          toolchain
          sdkVersion
          ;
      } args).release
    else
      throw "racket-purifier: unknown target";
in
if profile then
  pkgs.writeText "racket-${target}-profile.json" (
    builtins.toJSON {
      inherit output;
      sdk = builtins.storePath sdk;
    }
  )
else
  output
