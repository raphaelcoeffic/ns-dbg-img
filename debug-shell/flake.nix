{
  description = "A debug shell";
  inputs = {
    nixpkgs.url = "flake:nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    { self, nixpkgs, flake-utils }:
      flake-utils.lib.eachDefaultSystem (system:
      let pkgs = import nixpkgs { inherit system; };
      in with pkgs; {
        packages = {
          default = pkgs.buildEnv {
            name = "debug-shell";
            paths = with pkgs; [
              coreutils
              curl
              diffutils
              dig
              findutils
              # fzf + zsh plugin
              git
              gnugrep
              gnused
              gnutar
              gzip
              helix
              htop
              iproute2
              iputils
              jq
              kitty.terminfo
              less
              lsof
              nano
              netcat-openbsd
              procps
              sngrep
              strace
              tcpdump
              util-linux
              vim
              zsh
            ];
          };
        };
      }
    );
}
