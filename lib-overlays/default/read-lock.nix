{ lib }:
{
  src,
  lockFile ? src + "/racket-purifier.lock.json",
}:
let
  raw = if builtins.pathExists lockFile then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  entries = data.entries or [ ];
  nodes = data.packages or [ ];
  inputs = data.inputs or { };
  relative =
    s: builtins.isString s && !(lib.hasPrefix "/" s) && !(builtins.elem ".." (lib.splitString "/" s));
  safe =
    s: builtins.isString s && s != "." && s != ".." && builtins.match "[A-Za-z0-9_.+-]+" s != null;
  sha1 = s: builtins.isString s && builtins.match "[0-9a-f]{40}" s != null;
  sri = s: builtins.isString s && builtins.match "sha256-[A-Za-z0-9+/]{43}=" s != null;
  valid =
    (data.version or null) == 1
    && (data.purifier or null) == "racket"
    && (data.vm or null) == "chez-scheme"
    && builtins.isList (data.extraInputs or null)
    && builtins.all relative data.extraInputs
    && builtins.isAttrs inputs
    &&
      builtins.attrNames inputs
      == builtins.sort builtins.lessThan (lib.unique ([ "info.rkt" ] ++ data.extraInputs))
    && builtins.all (
      name:
      relative name
      && name != ""
      && builtins.isAttrs inputs.${name}
      && builtins.isString (inputs.${name}.content or null)
      && builtins.pathExists (src + "/${name}")
      && (builtins.readDir (dirOf (src + "/${name}"))).${baseNameOf name} == "regular"
      && builtins.hashFile "sha256" (src + "/${name}") == (inputs.${name}.sha256 or null)
      && builtins.hashString "sha256" inputs.${name}.content == inputs.${name}.sha256
    ) (builtins.attrNames inputs)
    && builtins.isAttrs (data.project or null)
    && safe (data.project.name or null)
    && builtins.isString (data.project.version or null)
    && builtins.isList (data.sdkPackages or null)
    && builtins.all (
      p: builtins.isAttrs p && safe (p.name or null) && sha1 (p.checksum or null)
    ) data.sdkPackages
    && builtins.isList entries
    && builtins.all (
      e:
      builtins.isAttrs e
      && relative (e.path or null)
      && e.path != ""
      && sri (e.hash or null)
      && (
        if e ? git then
          lib.hasPrefix "git/" e.path
          && builtins.isAttrs e.git
          && builtins.isString (e.git.url or null)
          && sha1 (e.git.rev or null)
          && (e.git.submodules or null) == false
          && (e.git.leaveDotGit or null) == false
          && e.git ? commitObject
          && e.git.commitObject == null
          && !(e ? url)
        else
          lib.hasPrefix "archives/" e.path
          && builtins.isString (e.url or null)
          && lib.hasPrefix "https://" e.url
          && (e.mirrors or null) == [ ]
      )
    ) entries
    && builtins.length (lib.unique (map (e: e.path) entries)) == builtins.length entries
    && builtins.isList nodes
    && builtins.all (
      p:
      builtins.isAttrs p
      && safe (p.name or null)
      && sha1 (p.checksum or null)
      && relative (p.subpath or null)
      && builtins.isString (p.source or null)
      && builtins.elem (p.type or null) [
        "file-url"
        "git"
        "git-url"
        "github"
      ]
      && builtins.any (
        e:
        e.path == (p.entry or null)
        && (
          if p.type == "file-url" then
            !(e ? git) && e.url == p.source && p.subpath == ""
          else
            e ? git && e.git.rev == p.checksum
        )
      ) entries
    ) nodes
    && builtins.length (lib.unique (map (p: p.name) nodes)) == builtins.length nodes
    && builtins.all (e: builtins.any (p: p.entry == e.path) nodes) entries
    && builtins.isAttrs (data.toolVersions or null)
    && builtins.all (key: builtins.isString (data.toolVersions.${key} or null)) [
      "sdk"
      "racket"
      "gcc"
    ];
in
{
  purifier = "racket";
  inherit data entries;
  problems = lib.optional (
    !valid
  ) "Racket lock is missing, stale, or unsupported; run racket-purifier lock --update";
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
}
