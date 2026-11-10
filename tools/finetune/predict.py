"""Run a (fine-tuned) student model over an exported evaluation file, timing each line.

Usage: uv run --project tools/finetune python tools/finetune/predict.py MODEL_DIR DATA.jsonl OUT.jsonl [--adapter DIR]
"""

import argparse
import json
import time

from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler


def prompt_for(tokenizer, messages):
    # Thinking off: the empty think block is part of the prompt, as in training targets.
    return tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, enable_thinking=False, tokenize=False
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("data")
    parser.add_argument("out")
    parser.add_argument("--adapter")
    args = parser.parse_args()
    model, tokenizer = load(args.model, adapter_path=args.adapter)
    sampler = make_sampler(temp=0.0)
    rows = [json.loads(line) for line in open(args.data)]
    generate(model, tokenizer, prompt_for(tokenizer, rows[0]["messages"][:2]), max_tokens=8, sampler=sampler)  # warm up
    with open(args.out, "w") as out:
        for row in rows:
            started = time.perf_counter()
            text = generate(model, tokenizer, prompt_for(tokenizer, row["messages"][:2]),
                            max_tokens=160, sampler=sampler)
            ms = round((time.perf_counter() - started) * 1000)
            out.write(json.dumps({"meta": row["meta"], "output": text, "ms": ms}, ensure_ascii=False) + "\n")
    print(f"{len(rows)} predictions -> {args.out}")


if __name__ == "__main__":
    main()
