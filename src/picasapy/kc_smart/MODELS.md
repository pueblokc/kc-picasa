# KC Smart Search model

| | |
|---|---|
| Model id (in `embeddings.db`) | `clip-vit-b32-q8` |
| Base model | OpenAI CLIP ViT-B/32 (`openai/clip-vit-base-patch32`) |
| ONNX export | Hugging Face repo `Xenova/clip-vit-base-patch32` |
| Pinned revision | `6b7c523703ae26e39be4b03774966f8571c7f523` |
| Licence | MIT (repo card `license: mit`; OpenAI CLIP code and weights are MIT) |
| Embedding | 512-d, L2-normalized, stored as float16 |
| Runtime | `onnxruntime`, CPU execution provider |
| Total download | 155.0 MB (155,008,455 bytes) |

## Files

Downloaded from
`https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/<revision>/<file>`
into `<data_dir>/kc-smart/models/clip-vit-b32-q8/`.

| File | Bytes | sha256 |
|---|---:|---|
| `onnx/vision_model_quantized.onnx` | 89,117,001 | `583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299` |
| `onnx/text_model_quantized.onnx` | 64,504,507 | `73baab855d406190da9faa498cfedf65f15cf309f4cc7385b7b032e6d08e5c3a` |
| `vocab.json` | 862,328 | `5047b556ce86ccaf6aa22b3ffccfc52d391ea4accdab9c2f2407da5b742d4363` |
| `merges.txt` | 524,619 | `9fd691f7c8039210e0fced15865466c65820d09b63988b0174bfe25de299051a` |

The ONNX files are 8-bit dynamically quantized exports. Inputs and outputs:

- vision: `pixel_values` float32 `[N, 3, 224, 224]` -> `image_embeds` `[N, 512]`
- text: `input_ids` int64 `[N, L]` -> `text_embeds` `[N, 512]` (no attention mask;
  pad with the end token 49407)

Preprocessing (from the repo's `preprocessor_config.json`): shortest edge to
224 bicubic, centre crop 224, scale to 0..1, normalize with mean
`(0.48145466, 0.4578275, 0.40821073)` and std `(0.26862954, 0.26130258, 0.27577711)`.

## Download behaviour

- Each file goes to `<name>.part` first. A later run continues with an HTTP
  `Range` request, so an interrupted download resumes.
- The finished file is hashed. A mismatch deletes it and raises
  `ModelDownloadError`; only verified files get their final name.
- `KC_SMART_MODEL_BASE_URL` (or `ensure_models(base_url=...)`) points the
  download at a mirror that uses the same `/<repo>/resolve/<rev>/<file>` layout.

## Tokenizer

`tokenizer.py` is a pure-Python CLIP BPE tokenizer (no torch, transformers or
`tokenizers`). It matches the Hugging Face fast tokenizer for this repo. The
tests compare it against ids from the `tokenizers` library.

## Changing the model

Add a new `ModelSpec` in `model.py` with a new `model_id`. `SmartIndex`
stores the model id and drops every stored vector when it changes, so the
library is re-embedded with the new model.
