#!/bin/sh

oops() {
    echo "$0:" "$@" >&2
    exit 1
}

umask 0022

tmpDir="$1/tmp"
mkdir -p $tmpDir

require_util() {
    command -v "$1" > /dev/null 2>&1 ||
        oops "you do not have '$1' installed, which is needed to $2"
}

case "$(uname -s).$(uname -m)" in
    Linux.x86_64)
        hash=3c0779e4878d1289cf3fbb158ec5ea9bdf61dfb9b4efac6b3b0b6bec5ba4cf13
        path=0xf66gpzcg4924nkfz7cn4ynqrxcfglq/nix-2.24.9-x86_64-linux.tar.xz
        system=x86_64-linux
        ;;
    Linux.aarch64)
        hash=c57c2830bb407e02dacdf2b63c49cde273f905075b579f6d9a6114c669301f33
        path=6wjg39ajzfmg0v5hz31ispz74lf59c72/nix-2.24.9-aarch64-linux.tar.xz
        system=aarch64-linux
        ;;
    *) oops "sorry, your system is not supported";;
esac

url=https://releases.nixos.org/nix/nix-2.24.9/nix-2.24.9-$system.tar.xz
tarball=$tmpDir/nix-2.24.9-$system.tar.xz

require_util tar "unpack the binary tarball"
if [ "$(uname -s)" != "Darwin" ]; then
    require_util xz "unpack the binary tarball"
fi

if command -v curl > /dev/null 2>&1; then
    fetch() { curl --fail -L "$1" -o "$2"; }
elif command -v wget > /dev/null 2>&1; then
    fetch() { wget "$1" -O "$2"; }
else
    oops "you don't have wget or curl installed, which is needed to download the binary tarball"
fi

echo "downloading Nix 2.24.9 binary tarball for $system from '$url' to '$tmpDir'..."
fetch "$url" "$tarball" || oops "failed to download '$url'"

if command -v sha256sum > /dev/null 2>&1; then
    hash2="$(sha256sum -b "$tarball" | cut -c1-64)"
elif command -v shasum > /dev/null 2>&1; then
    hash2="$(shasum -a 256 -b "$tarball" | cut -c1-64)"
elif command -v openssl > /dev/null 2>&1; then
    hash2="$(openssl dgst -r -sha256 "$tarball" | cut -c1-64)"
else
    oops "cannot verify the SHA-256 hash of '$url'; you need one of 'shasum', 'sha256sum', or 'openssl'"
fi

if [ "$hash" != "$hash2" ]; then
    oops "SHA-256 hash mismatch in '$url'; expected $hash, got $hash2"
fi

unpack="$1"/unpack
mkdir -p "$unpack"
tar -xJf "$tarball" -C "$unpack" || oops "failed to unpack '$url'"
