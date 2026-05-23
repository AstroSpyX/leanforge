# SPIKES — pre-code findings

## Spike 1 step a — Ollama library existence check (2026-05-22)

Method: HTTP GET against `https://ollama.com/library/<name>` and a
search-page sweep for math/prover keywords. Note: the HEAD-based
check in the spec is misleading — Ollama returns 405 (Method Not
Allowed) on HEAD for valid models and 404 for missing ones, but
the 405 vs 404 distinction is brittle. **Spec should be updated to
use GET, not HEAD.**

### Results for the originally planned 5 models

| Key       | Slug tried              | HTTP | Verdict                  |
|-----------|-------------------------|------|--------------------------|
| llama     | llama3.1                | 200  | in library               |
| phi       | phi4                    | 200  | in library               |
| qwen      | qwen2.5-math            | 404  | NOT in library           |
| kimina    | kimina-prover           | 404  | NOT in library (GGUF)    |
| deepseek  | deepseek-prover-v2      | 404  | NOT in library (GGUF)    |

`qwen2.5-math` specifically is not in the Ollama library at any slug
I tried. `qwen2-math:7b` (one major version older) exists and was
chosen as the substitute.

### Revised lineup (confirmed)

| Key       | Ollama name              | Source            |
|-----------|--------------------------|-------------------|
| kimina    | kimina-prover (custom)   | GGUF route        |
| deepseek  | deepseek-prover (custom) | GGUF route        |
| qwen      | qwen2-math:7b            | official library  |
| llama     | llama3.1:8b              | official library  |
| phi       | phi4:14b                 | official library  |

## Spike 1 step b — RAM and disk measurement (2026-05-23)

Bug in the original measurement script: `timeout` is not on macOS
by default, and zsh's `${PIPESTATUS[0]}` syntax differs from
bash's. Pulls completed correctly; RAM was measured manually
afterward via `ollama run "$m" "tiny prompt"; ollama ps`.

| Model           | Disk    | Pull   | Resident RAM | Default ctx | Cold start |
|-----------------|---------|--------|--------------|-------------|------------|
| qwen2-math:7b   | 4.4 GB  | 58 s   | 4.7 GB       | 4096        | ~19 s      |
| llama3.1:8b     | 4.9 GB  | 64 s   | 11 GB        | 32768       | ~13 s      |
| phi4:14b        | 9.1 GB  | 114 s  | 14 GB        | 16384       | ~6 s       |

All three run 100% on GPU via Apple Metal — no CPU fallback. Sum of
resident sizes (~30 GB) is close to the 36 GB ceiling. Ollama
evicts the LRU model when memory pressure crosses the limit, which
is correct but means simultaneous queries to all three would thrash.

### Important: per-model context-window surprises

The "resident RAM" column is dominated by the KV cache for the
default context window, not the weights themselves:

  - **qwen2-math:7b** ships with `num_ctx=4096`. This is tiny and
    will not fit a fix-mode prompt (source + diagnostics + imports
    can easily exceed 4 K tokens). Either override num_ctx via the
    Modelfile / API parameter or accept truncation.
  - **llama3.1:8b** defaults to `num_ctx=32768` (not its full 128 K).
    Resident jumps to 11 GB because of the KV cache.
  - **phi4:14b** defaults to `num_ctx=16384`. Resident is 14 GB.

These observed defaults are what Ollama configures, NOT the model's
maximum. Update `models.py num_ctx` to match the Ollama defaults
(or override explicitly).

Cold-start variance (19 / 13 / 6 s) is suspicious for phi4 — it
likely benefitted from filesystem cache after the back-to-back
pulls. Treat these as rough order-of-magnitude, not benchmark data.

## Spike 2 — HuggingFace model cards (2026-05-23)

### DeepSeek-Prover-V2-7B (deepseek-ai/DeepSeek-Prover-V2-7B)

**Prompt format** — chat template with one user turn. The exact
content the model expects:

    Complete the following Lean 4 code:

    ```lean4
    [FORMAL_STATEMENT]
    ```

    Before producing the Lean 4 code to formally prove the given
    theorem, provide a detailed proof plan outlining the main proof
    steps and strategies. The plan should highlight key ideas,
    intermediate lemmas, and proof structures that will guide the
    construction of the final formal proof.

Used via `tokenizer.apply_chat_template(chat, add_generation_prompt=True)`.
No system message in the published example.

**num_ctx**: 32768 (32K tokens) — explicitly documented as
"extended context length of up to 32K tokens."

**Decoding**: no temperature/top_p specified in the published
example. Only `max_new_tokens=8192`.

**GGUFs**: multiple community quantizations available, all
suitable for Ollama:
  - `unsloth/DeepSeek-Prover-V2-7B-GGUF` (broad quant range)
  - `mradermacher/DeepSeek-Prover-V2-7B-GGUF`
  - `irmma/DeepSeek-Prover-V2-7B-Q4_K_M-GGUF`
  - `NikolayKozloff/DeepSeek-Prover-V2-7B-Q8_0-GGUF`

Recommendation: `unsloth` or `mradermacher` for the widest selection
of quant levels. Q5_K_M or Q6_K is the right tradeoff for math
reasoning on 36 GB RAM.

### Kimina-Prover-Preview-Distill-7B (AI-MO/Kimina-Prover-Preview-Distill-7B)

**Prompt format** — chat template with system + user messages:

    [system]: You are an expert in mathematics and Lean 4.
    [user]:   <problem prompt>

Used via `tokenizer.apply_chat_template(messages, add_generation_prompt=True)`.

**num_ctx**: not documented on this 7B page. The larger 72B
sibling supports `max_model_len=131072`, so the 7B is likely at
least 32K. **Assume 32768 in the registry until measured.**

**Decoding** — explicitly recommended in the published example,
and importantly NOT temperature=0:

    SamplingParams(temperature=0.6, top_p=0.95, max_tokens=8096)

**Implication for the spec**: our `temperature=0.0` default will
underperform on Kimina specifically. The model was trained for
sampling, not greedy decoding. Either:
  - Allow per-model default temperature in `ModelConfig` and set
    Kimina's to 0.6
  - Or call out in the registry that Kimina users should pass
    `temperature=0.6` explicitly

The first is cleaner. **Spec should be updated to add
`default_temperature: float` to ModelConfig.**

**GGUFs**: community quantizations available:
  - `mradermacher/Kimina-Prover-Preview-Distill-7B-GGUF` —
    Q2_K through F16 (Q4_K_M = 4.8 GB, Q5_K_M = 5.5 GB,
    Q6_K = 6.4 GB recommended for quality)
  - `DevQuasar/AI-MO.Kimina-Prover-Preview-Distill-7B-GGUF`

Recommendation: `mradermacher/...` at Q6_K (6.4 GB). The mradermacher
README explicitly tags Q4_K_S/Q4_K_M as "fast, recommended" but for
proof reasoning Q6_K is the sweet spot.

### Knock-on spec updates this surfaces

1. Add `default_temperature: float` to `ModelConfig` and have
   `ask_llm`'s `temperature` parameter fall back to it instead of a
   hard-coded 0.0. Kimina default: 0.6. Others: 0.0.
2. The GGUF section in the spec can be simpler than written —
   for these two models we don't run llama.cpp conversion at all,
   we just download the published `.gguf` file and write a 3-line
   Modelfile. Update the GGUF recipe to lead with "download the
   published GGUF" and treat from-scratch conversion as a separate
   last-resort fallback.

## Spike 1 step b (continued) — Prover models via GGUF route

GGUFs downloaded into `llm/gguf-cache/`, registered with Ollama via
3-line Modelfiles, then loaded for measurement.

| Model                     | GGUF source                                          | Size on disk | Resident (GPU) | First-inference wall |
|---------------------------|------------------------------------------------------|--------------|----------------|----------------------|
| kimina-prover:q6_k        | mradermacher/Kimina-Prover-Preview-Distill-7B-GGUF   | 5.8 GB       | 7.7 GB         | ~12 s (cold)         |
| deepseek-prover:q5_k_m    | unsloth/DeepSeek-Prover-V2-7B-GGUF                   | 4.6 GB       | **22 GB**      | ~2 s (warm cache)    |

### Surprise: deepseek-prover at 22 GB resident

DeepSeek's 22 GB GPU footprint at num_ctx=32768 is more than 3x
Kimina's footprint at num_ctx=16384. Some of this is from the
2x context (KV cache scales linearly), but not all of it —
22 GB is unexpectedly large for a 7B at Q5_K_M. Two possibilities:

  - DeepSeek-Prover-V2 may have an unusual architecture (e.g.,
    MoE expansion in RAM that doesn't appear in the GGUF file size)
  - Ollama allocated extra compute/scratch buffers at the larger ctx

Practical impact: with both prover models loaded simultaneously we
exceed 36 GB unified RAM. Cannot run kimina + deepseek + any other
model concurrently. Need to ensure ask_llm doesn't try to.

Mitigation if needed: lower DeepSeek's num_ctx in its Modelfile
(re-create at e.g. 16384) to halve the KV cache.

### Gotchas captured during the spike

- `huggingface-cli` has been renamed to `hf` in recent
  huggingface_hub versions. Old syntax silently prints help and
  exits 0. Spec should reference `hf download`.
- Filenames in HF GGUF repos vary by uploader. `unsloth/...`
  prefixes filenames with the full model name
  (`DeepSeek-Prover-V2-7B-Q5_K_M.gguf`), while `mradermacher/...`
  uses a dot separator (`Kimina-Prover-Preview-Distill-7B.Q6_K.gguf`).
  Always verify exact filename via HF API before downloading.
- `echo "prompt" | ollama run MODEL | tail -3` hangs because
  `ollama run` doesn't reliably exit on stdin EOF + the downstream
  `tail` buffers until pipe closure. Use `ollama run MODEL "prompt"`
  (prompt as arg) or the HTTP API directly. Spec should reflect.
- Both prover models, when given a bare "hi" prompt without their
  trained Lean-formatted wrapper, behave like generic chatty LLMs
  ("having trouble with this problem", "I have a problem with the
  following question..."). This confirms the importance of the
  per-model formatters in prompts.py — sending raw text gives
  generic-model responses, not proof-model behavior.

## Spike 2 status — DONE

Both HF cards read, prompt formats and decoding params captured
above. Ready to inform `prompts.py fmt_kimina_*` and
`fmt_deepseek_*` when implementation starts.

## Spike 3 — actual eval, all 5 models on a real Lean theorem (2026-05-23)

Single prompt across all 5 models: prove `Irrational (Real.sqrt 2)`
in Lean 4 with Mathlib. Same chat-format messages array sent to
each. Sampling at temperature=0.6, top_p=0.95, num_predict=1500.
Full curls in `llm/evals/curls.txt`.

### Results

| Model                    | tok/s | Tokens | Verdict on Lean output                          |
|--------------------------|------:|-------:|-------------------------------------------------|
| kimina-prover:q6_k       |  22   | 741    | Syntactically valid, self-reference bug (1-line fix) |
| qwen2-math:7b            |  30   | 755    | Total fiction — Lean 3/4 mix, invented identifiers   |
| llama3.1:8b              |  27   | 568    | Invented Lean, more Lean-aware vocab but still fiction |
| phi4:14b                 |  15   | 922    | Invented, heavy Lean 3 namespace bleed              |
| deepseek-prover:q5_k_m   |  —    | 1      | **Empty response** — naive format hit EOS immediately |

### DeepSeek's three confirmed failure modes

| Config                                       | Result                                  |
|----------------------------------------------|------------------------------------------|
| Shared chat format + system message + 0.6    | 1 token, empty                          |
| Proper "Complete the following..." + temp=0  | 1500-token repetition loop, no Lean code |
| Proper wrapper + temp=0.6                    | Fluent gibberish proof plans, no Lean code, broken English |

Diagnosis: likely chat-template mismatch in the unsloth GGUF +
extreme format rigidity from training. Tried Q5_K_M; higher quant
might help marginally but architectural fragility is the real issue.

### Headline findings

1. **None of the 5 models produced compilable Lean.** Kimina came
   closest but still emitted a bug (self-referential `apply`).

2. **Specialization beats scale.** Kimina (7B prover) produced
   better-shaped Lean than phi4 (14B generalist) at half the
   throughput cost — but neither is correct.

3. **Generalists hallucinate Lean identifiers confidently.**
   qwen2-math, llama3.1, phi4 all invented Mathlib lemma names,
   mixed Lean 3 / Lean 4 syntax, and produced "fluent gibberish"
   that looks like Lean at a glance.

4. **Prover models are format-rigid.** Kimina has hard-baked
   chain-of-thought (cannot be prompted away); DeepSeek fails
   silently or loops when the format is off.

5. **Chain-of-thought is unfixable by prompting.** Tried strong
   "output ONLY code" system prompts on Kimina. Ignored every time.
   The reliable answer is post-process (extract last `lean4` fence).

### Gotchas captured (general)

- `huggingface-cli` was renamed to `hf` in recent `huggingface_hub`
  versions. Old syntax silently exits 0 with help output.
- HF GGUF filenames vary by uploader (`unsloth/...` prefixes with
  full model name, `mradermacher/...` uses a dot separator). Verify
  via `https://huggingface.co/api/models/<repo>` before downloading.
- `echo "prompt" | ollama run MODEL | tail -3` hangs because
  `ollama run` doesn't exit on stdin EOF and downstream `tail`
  buffers. Use `ollama run MODEL "prompt"` or the HTTP API.
- macOS lacks `timeout` by default (use `gtimeout` from coreutils
  or skip the cap).
- zsh's `${PIPESTATUS[0]}` is not bash-compatible.

### Decision: pivot to Anthropic API

The local 7-14B class cannot reliably produce correct novel Lean 4
code. Per the spec rev 4 (LLM.spec.txt), the leanforge LLM stage
will be driven by Claude (default: Sonnet 4.6, escalate to Opus
4.7 for hard cases, use Haiku 4.5 for routing).

The Ollama setup, GGUFs, and Modelfiles are kept on disk as a
documented option for future offline/triage use. The Spike work
documented here is not wasted — it established baseline behavior
for small local models on this task and gave us concrete reasons
to choose Claude.

## All spike work complete

Spikes 1a, 1b (in-library + GGUF route), 2 (HF cards), and 3
(actual eval) are done. The findings inform the new
`LLM.spec.txt` revision 4 (Anthropic API).

Next: implement `models.py` per BUILD ORDER step 1 of spec rev 4
(small registry of three Claude model IDs).
