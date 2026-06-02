# leanforge

An agentic repair loop for Lean 4. Point it at a broken Lean file and a
goal in plain English; it runs the Lean LSP, feeds the structured
diagnostics to an LLM, applies the edits, re-checks, and iterates until
the file compiles (or it hits a cost/iteration budget).

It has two parts:

- **`leanforge.py`** — a diagnostics extractor. Lean 4 file → JSON with
  every diagnostic enriched by the same context the VS Code InfoView
  shows: proof goal, expected type, enclosing declaration, source
  snippet. (`lean --json` only gives you the raw message.)
- **`refine/`** — the agentic loop that uses those diagnostics to drive
  an LLM (Claude or Gemini) through iterative fixes, with per-run
  snapshots, a response cache, and a cost ceiling.

## Requirements

- Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/)
- A Lean toolchain via [elan](https://lean-lang.org/lean4/doc/setup.html)
- An `ANTHROPIC_API_KEY` (and `GOOGLE_API_KEY` for Gemini models)

## Setup

```bash
cp .env.example .env   # then add your API key(s)
```

Dependencies are declared in `pyproject.toml` and resolved on demand by
`uv run --group runtime` — no separate install step needed.

## Usage

Run the repair loop on a Lean file:

```bash
uv run --group runtime --python 3.12 -m refine \
    --project-root examples/scratch \
    --file Scratch/Challenge.lean \
    --goal "Replace the sorrys with valid Lean 4 proofs." \
    --mode auto \
    --max-iters 3 \
    --max-cost-usd 0.10
```

Or just extract diagnostics as JSON:

```bash
uv run --group runtime --python 3.12 leanforge.py path/to/File.lean
```

See `RUN_COMMANDS.txt` for the full command set — inspecting per-run
state, the LLM cache, and the QA pipeline.

## Additional docs

- [PROJECT_LOG.txt](PROJECT_LOG.txt) — running narrative history of the project.
- [IMPROVEMENTS.txt](IMPROVEMENTS.txt) — backlog and ideas for future work.
- [llm/LOCAL_MODELS.txt](llm/LOCAL_MODELS.txt) — archived local-model (Ollama) investigation.
- [llm/SPIKES.md](llm/SPIKES.md) — pre-code findings (local-model eval, JSON-mode decision, etc.).

## License

MIT — see [LICENSE](LICENSE).
