"""Download verified, pinned multilingual-E5-small model data only."""

import hashlib
import subprocess
from pathlib import Path

from huggingface_hub import hf_hub_download


MODEL_ID = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
WEIGHTS_SHA256 = "1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477"
DESTINATION = Path(__file__).resolve().parent / ".cache" / "embedding_multilingual" / REVISION


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for filename in ("config.json", "tokenizer_config.json", "tokenizer.json",
                     "special_tokens_map.json", "sentencepiece.bpe.model"):
        if not (DESTINATION / filename).is_file():
            hf_hub_download(repo_id=MODEL_ID, filename=filename,
                            revision=REVISION, local_dir=DESTINATION)
    weights = DESTINATION / "model.safetensors"
    if not weights.is_file() or file_hash(weights) != WEIGHTS_SHA256:
        url = f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/model.safetensors"
        subprocess.run(["curl.exe", "--fail", "--location", "--retry", "3",
                        "--continue-at", "-", "--silent", "--show-error",
                        "--output", str(weights), url], check=True)
    if file_hash(weights) != WEIGHTS_SHA256:
        raise RuntimeError("Pinned multilingual E5 safetensors SHA-256 mismatch")
    print(f"Verified {MODEL_ID}@{REVISION}; safetensors SHA-256 matches")


if __name__ == "__main__":
    main()
