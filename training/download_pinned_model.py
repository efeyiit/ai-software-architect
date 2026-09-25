"""Download only official pinned Qwen data files into the ignored local cache."""

import hashlib
import subprocess
from pathlib import Path

from huggingface_hub import hf_hub_download


MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
REVISION = "2e1fd397ee46e1388853d2af2c993145b0f1098a"
WEIGHTS_SHA256 = "c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8"
DESTINATION = Path(__file__).resolve().parent / ".cache" / "hf" / (
    "models--Qwen--Qwen2.5-Coder-1.5B-Instruct") / "snapshots" / REVISION


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for filename in ("config.json", "tokenizer_config.json", "tokenizer.json",
                     "vocab.json", "merges.txt", "generation_config.json"):
        if not (DESTINATION / filename).is_file():
            hf_hub_download(repo_id=MODEL_ID, filename=filename, revision=REVISION,
                            local_dir=DESTINATION)
    weights = DESTINATION / "model.safetensors"
    if not weights.is_file() or file_hash(weights) != WEIGHTS_SHA256:
        url = f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/model.safetensors"
        subprocess.run(["curl.exe", "--fail", "--location", "--retry", "3",
                        "--continue-at", "-", "--output", str(weights), url], check=True)
    if file_hash(weights) != WEIGHTS_SHA256:
        raise RuntimeError("Official pinned model weight SHA-256 mismatch")
    print(f"Verified official model revision {REVISION} and weights SHA-256 {WEIGHTS_SHA256}")


if __name__ == "__main__":
    main()
