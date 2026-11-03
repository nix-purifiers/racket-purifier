{
  symlinkJoin,
  nativeRacket,
  nix-prefetch-git,
  git,
  curl,
  cacert,
  gcc,
  gnumake,
  gnutar,
  gzip,
  unzip,
  coreutils,
  findutils,
}:
symlinkJoin {
  name = "racket-purifier-toolchain";
  paths = [
    nativeRacket
    nix-prefetch-git
    git
    curl
    cacert
    gcc
    gnumake
    gnutar
    gzip
    unzip
    coreutils
    findutils
  ];
}
