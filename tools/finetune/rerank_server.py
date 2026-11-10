"""Serve Qwen3-Reranker scores on loopback with MLX (docs/RERANKER-PLAN.md).

Usage: uv run --project tools/finetune python tools/finetune/rerank_server.py MODEL_DIR --port 8185

POST /v1/rerank {"instruction": str, "query": str, "documents": [str, ...]}
  -> {"scores": [float, ...], "total_ms": int}
Each score is the model's probability of "yes" against "no" for that document, in the prompt
format the model was trained with. GET /health answers when the model is loaded.
"""

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import mlx.core as mx
from mlx_lm import load
from mlx_lm.models.cache import make_prompt_cache

PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query "
    'and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n'
    "<|im_start|>user\n"
)
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
MAX_DOCUMENTS = 32
MAX_CHARS = 4000


class Scorer:
    def __init__(self, path: str):
        self.model, self.tokenizer = load(path)
        self.yes = self.tokenizer.convert_tokens_to_ids("yes")
        self.no = self.tokenizer.convert_tokens_to_ids("no")
        self.lock = threading.Lock()  # one forward pass at a time on the GPU

    def scores(self, instruction: str, query: str, documents: list[str]) -> list[float]:
        # The instruction and query are the same for every document: run them once and share
        # their keys and values across a batch of the documents' endings (about half the
        # time of scoring each full prompt). The split falls before the space that starts
        # the document, so the tokens are identical to the whole prompt's.
        head = self.tokenizer.encode(
            f"{PREFIX}<Instruct>: {instruction}\n<Query>: {query}\n<Document>:"
        )
        tails = [
            self.tokenizer.encode(f" {document}{SUFFIX}", add_special_tokens=False)
            for document in documents
        ]
        width = max(map(len, tails))
        pad = self.tokenizer.pad_token_id or 0
        with self.lock:
            cache = make_prompt_cache(self.model)
            self.model(mx.array([head]), cache=cache)
            for layer in cache:
                layer.keys = mx.repeat(
                    layer.keys[..., : layer.offset, :], len(tails), axis=0
                )
                layer.values = mx.repeat(
                    layer.values[..., : layer.offset, :], len(tails), axis=0
                )
            # Right padding: attention is causal, so padding after a document's ending cannot
            # change the logits at its last real token, where the yes/no answer is read.
            logits = self.model(
                mx.array([tail + [pad] * (width - len(tail)) for tail in tails]),
                cache=cache,
            )
            last = mx.stack([logits[n, len(tail) - 1] for n, tail in enumerate(tails)])
            pair = mx.softmax(
                mx.stack([last[:, self.no], last[:, self.yes]], axis=1), axis=1
            )
            mx.eval(pair)
        return [round(float(p), 6) for p in pair[:, 1].tolist()]


def handler(scorer: Scorer):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._send(200, {"status": "ok"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/v1/rerank":
                self._send(404, {"error": "not found"})
                return
            try:
                body = json.loads(
                    self.rfile.read(int(self.headers.get("Content-Length", 0)))
                )
                instruction, query = str(body["instruction"]), str(body["query"])
                documents = [str(d) for d in body["documents"]]
                if not documents or len(documents) > MAX_DOCUMENTS:
                    raise ValueError("between 1 and 32 documents")
                if any(len(t) > MAX_CHARS for t in [instruction, query, *documents]):
                    raise ValueError("text too long")
            except (ValueError, KeyError, TypeError) as error:
                self._send(400, {"error": str(error)})
                return
            started = time.perf_counter()
            scores = scorer.scores(instruction, query, documents)
            self._send(
                200,
                {
                    "scores": scores,
                    "total_ms": round((time.perf_counter() - started) * 1000),
                },
            )

        def log_message(self, *args):  # no request logging: queries are trainee lines
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("--port", type=int, default=8185)
    args = parser.parse_args()
    scorer = Scorer(args.model)
    scorer.scores("Warm up.", "Ready?", ["ready"])
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(scorer))
    server.serve_forever()


if __name__ == "__main__":
    main()
