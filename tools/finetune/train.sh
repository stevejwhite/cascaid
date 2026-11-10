#!/bin/sh
# Train a LoRA adapter for the student interpreter. Usage: tools/finetune/train.sh qwen3-0.6b [run-name]
# Optional: LORA_CONFIG=<yaml> (default lora.yaml), DATA=<dir> (default artifacts/finetune/data).
set -eu
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
name=$1; run=${2:-$name}
model=$(uv run --project "$here" --locked python -I "$here/download.py" "$name" | sed -n 's/^Verified .* in //p')
mkdir -p "$root/artifacts/finetune/runs/$run"
uv run --project "$here" --locked mlx_lm.lora --config "${LORA_CONFIG:-$here/lora.yaml}" --model "$model" \
  --data "${DATA:-$root/artifacts/finetune/data}" --adapter-path "$root/artifacts/finetune/runs/$run/adapter" \
  2>&1 | tee "$root/artifacts/finetune/runs/$run/train.log"
