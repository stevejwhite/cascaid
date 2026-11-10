// Copied into the HeadTTS install by tts:install and named as its transformersModule, so
// the worker loads Kokoro only from the verified local files and never downloads.
import { env } from "@huggingface/transformers";

env.allowRemoteModels = false;
env.allowLocalModels = true;
env.localModelPath = process.env.HEADTTS_MODEL_ROOT;
env.useFSCache = false;

export * from "@huggingface/transformers";
