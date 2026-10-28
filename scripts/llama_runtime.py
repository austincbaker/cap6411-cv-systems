#!/usr/bin/env python3
"""Prepare or serve the pinned CPU-only llama.cpp/SmolVLM profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPU_FLAGS = {
    "CMAKE_BUILD_TYPE": "Release",
    "GGML_CUDA": "OFF",
    "GGML_VULKAN": "OFF",
    "GGML_METAL": "OFF",
    "GGML_SYCL": "OFF",
    "GGML_OPENCL": "OFF",
    "GGML_RPC": "OFF",
    "LLAMA_OPENSSL": "OFF",
    "LLAMA_BUILD_TESTS": "OFF",
    "LLAMA_BUILD_EXAMPLES": "OFF",
    "LLAMA_BUILD_APP": "OFF",
    "LLAMA_BUILD_UI": "OFF",
    "LLAMA_USE_PREBUILT_UI": "OFF",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def run(*command: str) -> None:
    subprocess.run(command, check=True)


def prepare(profile: dict, cache: Path, models: Path, jobs: int) -> None:
    source = cache / "llama.cpp"
    cache.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        run(
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            profile["llama_cpp_release"],
            profile["llama_cpp_repository"],
            str(source),
        )
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if revision != profile["llama_cpp_revision"]:
        raise ValueError(
            "Cached llama.cpp revision differs from profile; use a fresh cache directory"
        )
    dirty = subprocess.check_output(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"],
        text=True,
    )
    if dirty:
        raise ValueError(
            "Cached llama.cpp source has local modifications; use a clean source cache"
        )
    run(
        "cmake",
        "-S",
        str(source),
        "-B",
        str(source / "build"),
        *(f"-D{name}={value}" for name, value in CPU_FLAGS.items()),
    )
    run(
        "cmake",
        "--build",
        str(source / "build"),
        "--target",
        "llama-server",
        "--parallel",
        str(jobs),
    )
    model_dir = models / profile["model_alias"]
    model_dir.mkdir(parents=True, exist_ok=True)
    for key in ("model", "projector"):
        artifact = profile[key]
        filename = artifact["filename"]
        if Path(filename).name != filename:
            raise ValueError("Profile artifact filenames must be simple basenames")
        target = model_dir / filename
        if target.exists():
            if digest(target) != artifact["sha256"]:
                raise ValueError(f"Existing artifact checksum mismatch: {target}")
            continue
        url = (
            f"https://huggingface.co/{profile['hf_repository']}/resolve/"
            f"{profile['hf_revision']}/{filename}"
        )
        temporary = target.with_suffix(target.suffix + ".part")
        print(f"Downloading {filename}", flush=True)
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if digest(temporary) != artifact["sha256"]:
            raise ValueError(f"Downloaded artifact checksum mismatch: {temporary}")
        temporary.replace(target)
    manifest = {
        "profile": profile,
        "observed_llama_cpp_revision": revision,
        "cmake_flags": CPU_FLAGS,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "binary": str(source / "build/bin/llama-server"),
        "artifacts": {
            key: {
                "path": str(model_dir / profile[key]["filename"]),
                "sha256": digest(model_dir / profile[key]["filename"]),
            }
            for key in ("model", "projector")
        },
    }
    (cache / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared CPU runtime: {cache / 'build-manifest.json'}", flush=True)


def serve(profile: dict, cache: Path, models: Path) -> None:
    manifest_path = cache / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["profile"] != profile or manifest["cmake_flags"] != CPU_FLAGS:
        raise ValueError("Build manifest differs from profile; run prepare first")
    binary = cache / "llama.cpp/build/bin/llama-server"
    command = [
        str(binary),
        "--model",
        str(models / profile["model_alias"] / profile["model"]["filename"]),
        "--mmproj",
        str(models / profile["model_alias"] / profile["projector"]["filename"]),
        "--alias",
        profile["model_alias"],
        "--device",
        "none",
        "--gpu-layers",
        "0",
        "--no-mmproj-offload",
        "--host",
        profile["host"],
        "--port",
        str(profile["port"]),
        "--threads",
        str(profile["threads"]),
        "--threads-batch",
        str(profile["threads"]),
        "--ctx-size",
        str(profile["context_size"]),
        "--parallel",
        "1",
        "--n-predict",
        str(profile["max_output_tokens"]),
        "--no-cache-prompt",
    ]
    for key in ("model", "projector"):
        artifact = models / profile["model_alias"] / profile[key]["filename"]
        if digest(artifact) != profile[key]["sha256"]:
            raise ValueError(f"Artifact checksum mismatch: {artifact}")
    (cache / "server-start.json").write_text(
        json.dumps(
            {"pid": os.getpid(), "command": command, "build_manifest": str(manifest_path)},
            indent=2,
        )
        + "\n"
    )
    os.execv(str(binary), command)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "serve"))
    parser.add_argument("--profile", type=Path, default=ROOT / "configs/inference.json")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache")
    parser.add_argument("--models-dir", type=Path, default=ROOT / "models")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs <= 0:
        parser.error("--jobs must be positive")
    try:
        profile = json.loads(args.profile.read_text())
        if args.action == "prepare":
            prepare(profile, args.cache_dir.resolve(), args.models_dir.resolve(), args.jobs)
        else:
            serve(profile, args.cache_dir.resolve(), args.models_dir.resolve())
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"Runtime setup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
