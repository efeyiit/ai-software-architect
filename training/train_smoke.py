"""Small local QLoRA CUDA smoke run with observable optimizer and reload checks."""

import argparse
import gc
import hashlib
import json
import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import bitsandbytes as bnb
import peft
import torch
import transformers
from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
REVISION = "2e1fd397ee46e1388853d2af2c993145b0f1098a"
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "synthetic_smoke.jsonl"
CACHE = ROOT / ".cache" / "hf"
MODEL_PATH = CACHE / "models--Qwen--Qwen2.5-Coder-1.5B-Instruct" / "snapshots" / REVISION
EXPECTED_WEIGHTS_SHA256 = "c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8"
PROBE = "Write a Python function named clamp_value that clamps value between low and high."


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_from_weights():
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    return AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        local_files_only=True,
        trust_remote_code=False,
        use_safetensors=True,
        quantization_config=quantization,
        dtype=torch.float16,
        device_map={"": 0},
    )


def generate(model, tokenizer):
    model.eval()
    prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": PROBE}], tokenize=False, add_generation_prompt=True
    )
    tokens = tokenizer(prompt, return_tensors="pt").to("cuda")
    with torch.inference_mode():
        output = model.generate(**tokens, max_new_tokens=64, do_sample=False,
                                pad_token_id=tokenizer.eos_token_id)
    return tokenizer.decode(output[0, tokens.input_ids.shape[1]:], skip_special_tokens=True)


def example_tokens(tokenizer, record, max_length):
    user = {"role": "user", "content": record["instruction"]}
    assistant = {"role": "assistant", "content": record["response"]}
    prefix = tokenizer.apply_chat_template([user], tokenize=False, add_generation_prompt=True)
    complete = tokenizer.apply_chat_template([user, assistant], tokenize=False)
    prefix_ids = tokenizer(prefix, add_special_tokens=False).input_ids
    token_ids = tokenizer(complete, add_special_tokens=False).input_ids[:max_length]
    if len(prefix_ids) >= len(token_ids):
        raise ValueError("Example has no assistant tokens within context")
    labels = [-100] * len(prefix_ids) + token_ids[len(prefix_ids):]
    return (torch.tensor([token_ids], device="cuda"),
            torch.tensor([labels], device="cuda"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, choices=range(1, 21), required=True)
    parser.add_argument("--context", type=int, choices=(512, 1024), default=512)
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; CPU fallback is not a successful smoke run")
    if torch.cuda.get_device_properties(0).total_memory < 7_000_000_000:
        raise RuntimeError("GPU total VRAM below 7 GB; refusing likely OOM")
    random.seed(20260923)
    torch.manual_seed(20260923)
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    records = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines()]
    if len(records) < 50 or len(records) > 100:
        raise ValueError("Expected 50-100 original synthetic examples")
    if any(item.get("provenance") != "original synthetic smoke example; no quality evaluation"
           for item in records):
        raise ValueError("Unexpected data provenance")
    weights = MODEL_PATH / "model.safetensors"
    if not weights.is_file() or sha256_file(weights) != EXPECTED_WEIGHTS_SHA256:
        raise RuntimeError("Pinned official model.safetensors missing or SHA-256 mismatch")
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_PATH, local_files_only=True, trust_remote_code=False
    )
    model = model_from_weights()
    if not getattr(model, "is_loaded_in_4bit", False):
        raise RuntimeError("Weights were not actually loaded in 4-bit")
    baseline = generate(model, tokenizer)
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(
        r=4, lora_alpha=8, lora_dropout=0.0,
        target_modules=["q_proj", "v_proj"], bias="none", task_type="CAUSAL_LM"
    ))
    model.gradient_checkpointing_enable()
    trainable = {name: param for name, param in model.named_parameters() if param.requires_grad}
    if not trainable:
        raise RuntimeError("No trainable LoRA parameters")
    initial = {name: param.detach().cpu().clone() for name, param in trainable.items()}
    optimizer = torch.optim.AdamW(trainable.values(), lr=2e-4)
    model.train()
    order = list(range(len(records)))
    random.shuffle(order)
    losses = []
    processed_tokens = 0
    gradient_seen = False
    training_start = time.perf_counter()
    for step in range(args.steps):
        input_ids, labels = example_tokens(tokenizer, records[order[step]], args.context)
        optimizer.zero_grad(set_to_none=True)
        loss = model(input_ids=input_ids, labels=labels).loss
        if not torch.isfinite(loss):
            raise RuntimeError(f"Nonfinite loss at step {step + 1}: {loss.item()}")
        loss.backward()
        gradient_seen |= any(param.grad is not None and torch.any(param.grad != 0).item()
                             for param in trainable.values())
        torch.nn.utils.clip_grad_norm_(trainable.values(), 1.0)
        optimizer.step()
        torch.cuda.synchronize()
        processed_tokens += input_ids.numel()
        losses.append(float(loss.item()))
        print(f"step {step + 1}/{args.steps}: loss={losses[-1]:.5f} tokens={input_ids.numel()}", flush=True)
    training_seconds = time.perf_counter() - training_start
    max_delta = max(float((param.detach().cpu() - initial[name]).abs().max().item())
                    for name, param in trainable.items())
    if not gradient_seen or not math.isfinite(max_delta) or max_delta <= 0:
        raise RuntimeError("Optimizer did not produce a nonzero adapter weight update")
    checkpoint = ROOT / "checkpoints" / f"steps-{args.steps}"
    checkpoint.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(checkpoint, safe_serialization=True)
    adapter_file = checkpoint / "adapter_model.safetensors"
    if not adapter_file.is_file():
        raise RuntimeError("Adapter safetensors file missing")
    saved_state = {name: param.detach().cpu().clone() for name, param in trainable.items()}
    del model, optimizer, trainable, initial
    gc.collect()
    torch.cuda.empty_cache()
    reloaded = PeftModel.from_pretrained(model_from_weights(), checkpoint, is_trainable=False)
    reloaded_params = dict(reloaded.named_parameters())
    reload_max_delta = max(float((reloaded_params[name].detach().cpu() - before).abs().max().item())
                           for name, before in saved_state.items())
    if reload_max_delta > 1e-5:
        raise RuntimeError(f"Adapter reload mismatch: {reload_max_delta}")
    after = generate(reloaded, tokenizer)
    total_seconds = time.perf_counter() - started
    report = {
        "status": "passed", "purpose": "optimizer smoke only; no quality claim",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model_id": MODEL_ID, "model_revision": REVISION,
        "license": "Apache-2.0", "weights_format": "safetensors",
        "quantization": "NF4 4-bit with double quantization", "compute_dtype": "float16",
        "context_limit": args.context, "microbatch": 1, "gradient_checkpointing": True,
        "lora_rank": 4, "lora_targets": ["q_proj", "v_proj"],
        "synthetic_examples": len(records), "optimizer_steps": args.steps,
        "trainable_parameters": sum(v.numel() for v in saved_state.values()),
        "gradient_nonzero": gradient_seen, "adapter_max_weight_delta": max_delta,
        "adapter_reload_max_delta": reload_max_delta,
        "adapter_sha256": sha256_file(adapter_file),
        "losses": losses, "all_losses_finite": all(math.isfinite(x) for x in losses),
        "training_input_tokens": processed_tokens, "training_seconds": training_seconds,
        "effective_input_tokens_per_second": processed_tokens / training_seconds,
        "total_seconds_including_load_generation_reload": total_seconds,
        "peak_cuda_vram_mib": torch.cuda.max_memory_allocated() / 1024**2,
        "gpu": torch.cuda.get_device_name(0),
        "versions": {"torch": torch.__version__, "transformers": transformers.__version__,
                     "peft": peft.__version__, "bitsandbytes": bnb.__version__},
        "fixed_probe": PROBE, "before": baseline, "after": after,
    }
    output = ROOT / "reports" / f"steps-{args.steps}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    print(f"Report: {output}", flush=True)


if __name__ == "__main__":
    main()
