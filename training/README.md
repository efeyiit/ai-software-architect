# TRAIN-001: local QLoRA CUDA smoke test

This isolated experiment checks that a real optimizer updates a 4-bit model's
LoRA adapter, that the adapter can be saved as safetensors and reloaded, and
that a fixed prompt can be generated before and after. The 60 examples are
original, synthetic Python snippets. They are **not** a quality evaluation
dataset, and a loss change or changed generation does not prove better code.

## Model and constraints

- Publisher: [Qwen](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct)
- Model: `Qwen/Qwen2.5-Coder-1.5B-Instruct`
- Revision: `2e1fd397ee46e1388853d2af2c993145b0f1098a`
- License: Apache 2.0; weights: `model.safetensors`
- Loading: `trust_remote_code=False`, `use_safetensors=True`
- Method: NF4 4-bit quantization, double quantization, LoRA rank 4 on
  `q_proj`/`v_proj`, gradient checkpointing, float16 compute, microbatch 1.

The experiment requires NVIDIA CUDA. It deliberately refuses CPU fallback.
The training cache, virtual environment, checkpoints, and generated reports
are ignored by Git. No paid API or cloud service is used.

## Reproduce on Windows PowerShell

From the Ariadne repository root, with Python 3.12 and `uv` available:

```powershell
uv venv --python 3.12 training/.venv
$env:UV_CACHE_DIR = (Join-Path (Get-Location) 'training/.cache/uv')
uv pip install --python training/.venv/Scripts/python.exe torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python training/.venv/Scripts/python.exe -r training/requirements.txt
training/.venv/Scripts/python.exe training/make_synthetic_data.py
training/.venv/Scripts/python.exe training/download_pinned_model.py
training/.venv/Scripts/python.exe training/train_smoke.py --steps 1 --context 512
training/.venv/Scripts/python.exe training/train_smoke.py --steps 12 --context 512
```

The script prints each step and writes machine-readable reports to
`training/reports/`. These include finite losses, trainable parameter count,
gradient/update checks, adapter reload comparison, fixed prompt outputs,
CUDA peak allocated memory, elapsed time, and effective input tokens/second.
The adapter stays under `training/checkpoints/` and should be shared only
with the model's license and provenance attached.

## Verified local result (2026-09-23 UTC)

On an RTX 4060 Ti 8 GB with PyTorch 2.8.0+cu128, the one-step and 12-step
runs both passed. The 12-step run updated 544,768 LoRA parameters with a
maximum absolute weight change of 0.002450639. All 12 losses were finite;
the saved adapter reloaded with a maximum parameter difference of 0.0.
Training processed 958 input tokens in 4.16 seconds (230.27 input tokens/s)
and peak CUDA allocation was 2,000.05 MiB. The fixed prompt's generated
text changed after training, but no held-out quality test was performed.
These numbers demonstrate the local training mechanism only.

The 4.16 seconds time the training loop, including per-step tokenization,
CPU-to-CUDA transfer, forward/backward, optimizer, and synchronization. It
excludes model loading, initial/final generation, adapter saving/reloading.
The 958 input tokens include user prompts; only 308 assistant tokens were
supervised (74.03 supervised tokens/s). The 2,000.05 MiB is PyTorch's peak
CUDA **allocated** memory over the entire process, not peak reserved memory
or whole-device usage. These short examples cannot estimate full-length
training speed.

## TRAIN-002 synthetic pilot

`make_pilot_data.py` creates 72 source-grounded examples with complete
sequences of 518–572 tokens. Families are disjoint across 48 train, 12
validation, and 12 test records. Variants inside each family are closely
related; this is still a small synthetic pilot, not a final quality dataset.

```powershell
training/.venv/Scripts/python.exe training/make_pilot_data.py
training/.venv/Scripts/python.exe training/train_pilot.py --steps 100 --context 768
```

The 100-step CUDA run passed its training, save, and reload checks. A drop in
validation loss did **not** establish semantic improvement: both inspected
held-out outputs contained requirement violations. See `reports/pilot-100.json`
for the raw figures and the separate deliverable summary for interpretation.

## Sources

- [PyTorch Windows CUDA install](https://pytorch.org/get-started/locally/)
- [bitsandbytes Windows/CUDA support](https://huggingface.co/docs/bitsandbytes/installation)
- [PEFT 4-bit LoRA preparation](https://huggingface.co/docs/peft/developer_guides/quantization)
