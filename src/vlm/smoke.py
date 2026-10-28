"""Run repeated images through one existing local server and save the evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import uuid
from pathlib import Path

import httpx

from vlm.client import VLMClient, VLMConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=Path("configs/inference.json"))
    parser.add_argument("--image", type=Path, action="append", required=True)
    parser.add_argument("--repeat", type=int, default=2, help="Repeat the full image sequence")
    parser.add_argument("--max-tokens", type=int, help="Cannot exceed the profile bound")
    parser.add_argument("--output", type=Path, required=True, help="New run directory")
    args = parser.parse_args(argv)
    if args.repeat <= 0:
        parser.error("--repeat must be positive")
    try:
        profile = json.loads(args.profile.read_text())
        config = VLMConfig(
            base_url=f"http://{profile['host']}:{profile['port']}",
            model=profile["model_alias"],
            max_output_tokens=profile["max_output_tokens"],
            connect_timeout_s=profile["connect_timeout_s"],
            read_timeout_s=profile["read_timeout_s"],
        )
        bound = config.max_output_tokens if args.max_tokens is None else args.max_tokens
        if type(bound) is not int or not 0 < bound <= config.max_output_tokens:
            parser.error("--max-tokens must be within the positive profile bound")
        images = []
        for path in args.image:
            mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(
                path.suffix.lower(),
            )
            image = path.read_bytes()
            if mime is None or not image:
                parser.error("each image must be a nonempty encoded JPEG or PNG file")
            images.append((path, image, mime))
        args.output.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))

    manifest = {
        "record_version": 1,
        "run_id": uuid.uuid4().hex,
        "requested_profile": profile,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "completed": False,
        "requests": 0,
        "max_output_tokens": bound,
    }
    exit_code = 0
    try:
        with VLMClient(config) as client, (args.output / "requests.jsonl").open("x") as output:
            try:
                manifest["observed_server_properties"] = client.server_properties()
            except (httpx.HTTPError, ValueError) as exc:
                manifest["properties_error"] = type(exc).__name__
            for repeat in range(args.repeat):
                for index, (path, image, mime) in enumerate(images):
                    result = client.infer(
                        image,
                        frame_id=f"{repeat}:{index}",
                        source_id=str(path),
                        mime_type=mime,
                        max_tokens=bound,
                    )
                    record = {
                        **result.to_dict(),
                        "run_id": manifest["run_id"],
                        "image_sha256": hashlib.sha256(image).hexdigest(),
                    }
                    output.write(json.dumps(record) + "\n")
                    output.flush()
                    manifest["requests"] += 1
                    print(
                        json.dumps(
                            {
                                "frame_id": result.frame_id,
                                "status": result.status,
                                "elapsed_s": result.elapsed_s,
                                "text": result.text,
                            }
                        )
                    )
                    if not result.ok:
                        # Do not retry a request that might still be executing remotely.
                        manifest["error"] = result.status
                        exit_code = 1
                        break
                if exit_code:
                    break
            manifest["completed"] = exit_code == 0
    except KeyboardInterrupt:
        manifest["error"] = "interrupted"
        manifest["completed"] = False
        exit_code = 130
    except OSError as exc:
        manifest["error"] = type(exc).__name__
        manifest["completed"] = False
        exit_code = 1
    finally:
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
