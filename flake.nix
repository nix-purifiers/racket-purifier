{
  description = "Locked, Nix-resolved Racket dependencies";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      overlay = final: prev: {
        racket-purifier = final.lib.makeScope final.newScope (scope: {
          nativeRacket = final.racket-minimal;
          toolchain = scope.callPackage ./nix/toolchain.nix { };
          sdkVersion = import ./nix/sdk-version.nix { nixpkgsSrc = nixpkgs; };
          cli = scope.callPackage ./pkgs/racket-purifier/default.nix {
            nixpkgsSrc = nixpkgs;
            purifierSrc = purifier;
          };
          buildRacketProject = scope.callPackage ./pkgs/build-racket-project/default.nix {
            purifier = import (purifier + "/nix/lib") { inherit (final) lib; };
          };
        });
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      packages = forAll (system: {
        default = (pkgsFor system).racket-purifier.cli;
        cli = self.packages.${system}.default;
        sdk = (pkgsFor system).racket-purifier.toolchain;
      });
      lib.racket-purifier = import ./lib-overlays/default { lib = nixpkgs.lib; };
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/racket-purifier";
          meta.description = "Lock Racket dependencies";
        };
      });
      checks = forAll (
        system:
        let
          build = (pkgsFor system).racket-purifier.buildRacketProject { src = ./examples/minimal; };
        in
        {
          inherit (build.packages) environment project;
          release = build.release;
          cli = self.packages.${system}.default;
          installed = (pkgsFor system).runCommand "installed-racket-consumer" { } ''
            export HOME="$TMPDIR/home" PLTUSERHOME="$TMPDIR/home"
            mkdir -p "$HOME"
            ${build.packages.project}/bin/racket -e '(require purifier-example)' -e '(displayln (answer))' > answer
            ${(pkgsFor system).python3}/bin/python3 -c 'assert open("answer").read() == "42\n"'
            mkdir "$out"
            cp answer "$out/answer"
          '';
        }
      );
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
    };
}
