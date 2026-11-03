{ nixpkgsSrc }:
builtins.hashString "sha256" (
  builtins.toJSON {
    nixpkgs = toString nixpkgsSrc;
    toolchain = builtins.hashFile "sha256" ./toolchain.nix;
    config = builtins.hashFile "sha256" ../racket_purifier/config.rkt;
    install = builtins.hashFile "sha256" ../racket_purifier/install.rkt;
  }
)
