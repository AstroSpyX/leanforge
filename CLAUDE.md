# CLAUDE.md — project conventions

## Author name

Git commits authored by Claude on this project use the repo's local
git config:

```
user.name  = Pavlo
user.email = pavel.kiev@gmail.com
```

**Do NOT pass `git -c user.name=…` overrides.** The local repo config is
authoritative; let git pick it up. Past commits accidentally authored as
"Pavel" by me are a defect, not a precedent.

## Coding standards

All code in this repo follows `CODE_QUALITY_STANDARD.txt` (gitignored
local-only reference). The most load-bearing rules:

- B-4: no empty `__init__.py` (PEP 420 namespace packages)
- C-3: don't extract single-use helpers under 15 lines
- D-1: dataclasses for structured data
- E-2: specific generic types (`list[str]` not `list`)
- I-2: ≥90% branch coverage, `pytest --cov-branch`
- I-9: every test must catch a plausible bug
- K-2: no implicit `Any`; mypy `--strict` clean
- N-1: no `data`/`info`/`obj`/`temp` in identifiers

Run the QA pipeline before every commit:

```
uv run --with ruff --python 3.12 -- ruff check refine/
uv run --with ruff --python 3.12 -- ruff format --check refine/
uv run --with mypy --with pydantic --python 3.12 -- \
    mypy <modified files> --strict --ignore-missing-imports
uv run --with pytest --with pytest-cov --with pydantic --python 3.12 -- \
    python -m pytest refine/tests/ --cov=refine --cov-branch -q
```

## Specs

- `REFINE.spec.txt` — autonomous refinement loop (rev 4.1, implementation
  target). Build order at the end of the spec is authoritative.
- `LLM.spec.txt` — ask_llm component (Anthropic API + provider
  abstraction).
- `llm/SPIKES.md` — pre-code findings (local-model eval, JSON-mode
  decision, etc.).
- `llm/LOCAL_MODELS.txt` — archived Ollama investigation kept as
  documented option, not the active path.

## Secrets

- `.env` (gitignored) holds the real `ANTHROPIC_API_KEY`.
- `.env.example` (committed) is the template.
- `CODE_QUALITY_STANDARD.txt` is gitignored — local-only working file.
- Never commit secrets; never paste keys back into chat.

## Commit messages

- No "Co-Authored-By: Claude" or similar attribution lines unless the
  user explicitly asks.
- Title under 70 chars; body explains the why per change.
- One logical group per commit (per J-1 of the standard).

## Project log — keep PROJECT_LOG.txt current

`PROJECT_LOG.txt` (repo root) is the running narrative history of this
project. Newest entries at the top, separator `-------` between
entries. The format is shown in the file itself — match it.

**Update the log proactively** on substantial milestones, without
being asked. Use judgment about what counts as substantial.

LOG these:
- A bug found by running the system on real input (especially when
  the bug slipped past unit tests — that's the kind of finding the
  log exists to preserve)
- A new module or capability landing
- An architecture change (provider abstraction, schema bump, etc.)
- A version bump with user-visible behavior change
- A scope decision that changes what v1/v1.5/v2 mean
- A successful run on a meaningfully new kind of input (first
  Mathlib proof, first multi-file run, first OpenAI call, etc.)
- A spec revision that reasons through a non-obvious tradeoff

DON'T log these:
- Pure cosmetic refactors (ruff format passes, rename in one file)
- Adding a single test
- Doc-only edits to README/comments
- Configuration tweaks (pyproject.toml lint rules) unless they
  changed behavior
- WIP intermediate state

**Entry template:**

```
-------
YYYY-MM-DD — vX.Y.Z — one-line title
-------

  Short context (what was being done when this surfaced).

  Bug N — short name.
    What went wrong.
    Fix: what we did.

  Files: relative/path/a.py, relative/path/b.py.
```

For non-bug entries (new module, milestone, decision), keep the
same shape but use the appropriate prose. Always end with `Files:`
so a reader can jump to the actual change.

When committing alongside log updates: bundle the log entry with
the change it describes in the same commit, OR add the entry in
its own follow-up commit. Either is fine. Never let a substantial
change land without its log entry.
