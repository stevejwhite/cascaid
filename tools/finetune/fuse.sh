#!/bin/sh
# Merge a trained adapter into its base model and quantise it for fast inference.
# Usage: tools/finetune/fuse.sh qwen3-0.6b RUN [ADAPTER_DIR] [BITS]
# Writes artifacts/finetune/runs/RUN/fused-qBITS (an MLX model directory).
set -eu
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
name=$1; run=$2; dir="$root/artifacts/finetune/runs/$run"
adapter=${3:-$dir/adapter}; bits=${4:-4}
model=$(uv run --project "$here" --locked python -I "$here/download.py" "$name" | sed -n 's/^Verified .* in //p')
rm -rf "$dir/fused" "$dir/fused-q$bits"
uv run --project "$here" --locked mlx_lm.fuse --model "$model" --adapter-path "$adapter" --save-path "$dir/fused"
uv run --project "$here" --locked mlx_lm.convert --hf-path "$dir/fused" --mlx-path "$dir/fused-q$bits" -q --q-bits "$bits"
rm -rf "$dir/fused"
echo "Quantised student: $dir/fused-q$bits"
