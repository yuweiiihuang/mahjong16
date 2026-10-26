"""Build the opt-in POSIX MeowCaTS bridge from a clean, pinned upstream checkout."""
from __future__ import annotations

import argparse
import configparser
import json
from pathlib import Path
import shutil
import subprocess


UPSTREAM_COMMIT = "1e6ae5320d5e0d3d3b5d017ff83e05d02b9ba162"
ASSETS = Path(__file__).resolve().parents[1] / "bots/native/meowcats"


def build(upstream: Path, output: Path, *, sanitize: bool = False) -> None:
    """Preserve upstream; refuse existing output and initialize fresh native lookup tables."""
    upstream, output = upstream.resolve(), output.resolve()
    if output == upstream or upstream in output.parents:
        raise ValueError("Build output must be outside the upstream checkout")
    revision = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(upstream), "status", "--porcelain"], text=True).strip()
    if revision != UPSTREAM_COMMIT or dirty:
        raise ValueError("Expected a clean checkout of " + UPSTREAM_COMMIT)
    compiler = shutil.which("clang++") or shutil.which("g++")
    if compiler is None:
        raise RuntimeError("Install a C++17 clang++ or g++ compiler")
    output.mkdir(parents=True, exist_ok=False)
    vendor = output / "vendor"
    shutil.copytree(upstream, vendor, ignore=shutil.ignore_patterns(".git"))
    subprocess.run(["patch", "-p1", "-i", str(ASSETS / "compatibility.patch")],
                   cwd=vendor, check=True)
    shutil.copyfile(ASSETS / "bridge.cpp", output / "bridge.cpp")
    sources = json.loads((ASSETS / "sources.json").read_text())
    command = [compiler, "-std=c++17", "-DLINUX", "-pthread", "-O2", "-include", "cstdint",
               "-Ivendor/MJLibrary/Base", *["vendor/" + name for name in sources],
               "bridge.cpp", "-o", "bridge"]
    if sanitize:
        command += ["-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    (output / "build-command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (output / "build.log").open("w") as log:
        subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)
    runtime = output / "runtime"
    runtime.mkdir()
    shutil.copyfile(vendor / "ExplorationTermTable.txt", runtime / "ExplorationTermTable.txt")
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(vendor / "config.ini")
    for section, values in {
        "MCTS": {"TotalSampleCount": "2000", "ThreadNum": "0", "WaitReleaseTree": "1"},
        "BaseConfig": {"SampleCount": "2000", "SampleFirstRound": "100",
                       "SamplePerRound": "100"},
        "Multithread": {"ThreadNum": "0"}, "Debug": {"PrintDebugMsg": "0"},
        "Sgf": {"LogTreeSgf": "0", "LogGameSgf": "0"},
    }.items():
        config[section].update(values)
    with (runtime / "config.ini").open("w") as stream:
        config.write(stream)
    # Generate the native table here so normal startup need not exceed the search deadline.
    with (output / "initialize.log").open("w") as log:
        initialized = subprocess.run([str((output / "bridge").resolve())], cwd=runtime,
                                     input="", text=True, stdout=subprocess.PIPE, stderr=log,
                                     timeout=300, check=True)
    if initialized.stdout != "READY 1\n":
        raise RuntimeError("Bridge initialization failed its protocol self-check")
    print("Built", output / "bridge", "with runtime", runtime)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, help="Clean checkout at the documented commit")
    parser.add_argument("output", type=Path, help="New build directory; never overwritten")
    parser.add_argument("--sanitize", action="store_true", help="Enable ASan and UBSan")
    args = parser.parse_args()
    build(args.upstream.resolve(), args.output.resolve(), sanitize=args.sanitize)
