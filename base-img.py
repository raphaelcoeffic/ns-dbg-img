import os
import re
import ctypes
import shutil
import subprocess

from argparse import ArgumentParser
from pathlib import Path
from tempfile import TemporaryDirectory

_libc = ctypes.CDLL("libc.so.6")
assert _libc, "libc not loaded"

_get_errno_loc = _libc.__errno_location
_get_errno_loc.restype = ctypes.POINTER(ctypes.c_int)


def _errcheck(ret, func, args):
    if ret == -1:
        e = _get_errno_loc()[0]
        raise OSError(e, os.strerror(e))
    return ret


_mount = _libc.mount
_mount.restype = ctypes.c_int
_mount.argtypes = (
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_int,
    ctypes.c_void_p,
)
_mount.errcheck = _errcheck

_MS_BIND = 4096


def bind_mount(src: str, dst: str):
    return _mount(src.encode(), dst.encode(), "".encode(), _MS_BIND, 0)


NIX_CONF = """experimental-features = nix-command flakes
sandbox = false
build-users-group =
"""


def mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_path(base_path: Path) -> Path:
    return base_path / "store"


def cache_path(base_path: Path) -> Path:
    return base_path / ".cache"


def etc_path(base_path: Path) -> Path:
    return base_path / "etc"


def nix_paths(base_path: Path) -> tuple[Path, Path, Path]:
    return (
        store_path(base_path),
        cache_path(base_path),
        etc_path(base_path),
    )


def download_nix_script() -> str:
    return str(Path(__file__).parent / "scripts" / "dl-nix.sh")


def install_nix(path: Path) -> list[str]:
    """Install Nix into given path"""

    paths = nix_paths(path)
    store, cache, etc = paths

    if all(map(lambda p: p.exists(), paths)):
        return (cache / "base_paths").read_text().splitlines()

    nix_path = ""

    with TemporaryDirectory() as tmpdir:
        subprocess.run(
            [download_nix_script(), tmpdir],
            check=True,
        )
        tmp_store = next(Path(tmpdir).glob("**/store"), None)
        if not tmp_store:
            raise Exception("downloaded tarball did not contain any Nix store")

        install_script = tmp_store / ".." / "install"
        m = re.search(
            r'^nix="(/nix/store/[^"]*)"', install_script.read_text(), re.MULTILINE
        )
        if not m:
            raise Exception("could not detect Nix store path")

        nix_path = m.group(1)

        mkdir(path)
        shutil.copytree(
            tmp_store,
            store,
            symlinks=True,
        )
        os.symlink(Path(nix_path) / "bin", path / ".bin")

    # Adjust permissions
    subprocess.run(
        ["chmod", "-R", "a-w", *list(store.glob("*"))],
        check=True,
    )

    # Nix config
    mkdir(etc)
    nix_conf = etc / "nix.conf"
    if not nix_conf.exists():
        nix_conf.write_text(NIX_CONF)

    # Required....
    mkdir(path / "var" / "nix")

    # Write paths list into home/base_paths
    mkdir(cache)
    with (cache / "base_paths").open("w") as f:
        closure = list(
            map(
                lambda p: p.name,
                store.iterdir(),
            )
        )
        f.write("\n".join(closure) + "\n")
        return closure


def new_user_mount_ns():
    """Enter a new user+mnt namespace"""
    user_uid = os.getuid()
    user_gid = os.getgid()

    # Start with a fresh namespace (user + mnt)
    os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNS)

    # Map user into the new namespace
    uid_map = f"{user_uid} {user_uid} 1\n"
    with open("/proc/self/uid_map", "wb") as f:
        f.write(uid_map.encode())

    # Map group
    with open("/proc/self/setgroups", "wb") as f:
        f.write("deny".encode())

    gid_map = f"{user_gid} {user_gid} 1\n"
    with open("/proc/self/gid_map", "wb") as f:
        f.write(gid_map.encode())


def debug_shell_dir() -> str:
    return str(Path(__file__).parent / "debug-shell")


def build_base() -> tuple[Path, list[str]]:
    with TemporaryDirectory() as tmpdir:
        # Prepare runtime env
        env = dict(
            PATH="/nix/.bin:/usr/local/bin:/usr/bin:/bin",
            NIX_CONF_DIR="/nix/etc",
        )

        # Build base flake
        subprocess.run(
            ["nix", "build", debug_shell_dir()],
            check=True,
            cwd=tmpdir,
            env=env,
        )

        # Return store closure
        result_path = Path(tmpdir) / "result"
        p = subprocess.run(
            ["nix-store", "-qR", str(result_path)],
            text=True,
            check=True,
            capture_output=True,
            cwd=tmpdir,
            env=env,
        )

        path = result_path.readlink()
        closure = list(
            map(
                lambda p: Path(p).name,
                p.stdout.splitlines(),
            )
        )
        return (path, closure)


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("-p", "--path", type=Path, default=Path("./nix"))
    return parser.parse_args()


def main():
    args = parse_args()
    base_path = args.path

    # Install Nix package manager
    nix_closure = install_nix(base_path)

    # Mount the nix directories
    new_user_mount_ns()
    bind_mount(str(base_path), "/nix")

    # Build debug shell
    debug_shell_path, debug_shell_closure = build_base()

    with TemporaryDirectory() as tmpdir:
        keep_store_paths = set(nix_closure) | set(debug_shell_closure)

        def filter_store_paths(current_dir: str, entries: list[str]) -> list[str]:
            # Do not keep /nix/.cache
            if current_dir == "/nix":
                return list(
                    filter(
                        lambda p: p not in {".base", ".bin", "etc", "var", "store"},
                        entries,
                    )
                )

            if current_dir != "/nix/store":
                return []

            return list(
                filter(
                    lambda b: Path(b).name not in keep_store_paths,
                    entries,
                )
            )

        print(f"copying nix base into '{tmpdir}'")
        shutil.copytree(
            "/nix",
            tmpdir,
            ignore=filter_store_paths,
            symlinks=True,
            dirs_exist_ok=True,
        )
        base_link = Path(tmpdir, ".base")
        base_link.unlink(missing_ok=True)

        print(f"symlinking {str(base_link)} to {str(debug_shell_path)}")
        base_link.symlink_to(debug_shell_path)

        print("compressing base...")
        subprocess.run(
            [
                "tar",
                "cJf",
                "base.tar.xz",
                f"--directory={tmpdir}",
                ".",
            ],
            env=os.environ,
        )
        print("done")


if __name__ == "__main__":
    main()
