leanforge
=========

A command-line tool that reads a single Lean 4 source file and emits
one JSON document describing every diagnostic Lean produces for it,
enriched with the same context the VS Code InfoView shows: the proof
goal at each error, the expected type, the enclosing declaration, and
a source snippet around the error location.

The tool runs the Lean LSP server (`lake serve`) under the hood via
the `leanclient` Python library and consolidates several LSP calls
into one machine-readable output.


1. Goal
-------

Take a Lean file in. Get JSON out. The JSON contains, per diagnostic:

  - severity (error / warning / information / hint)
  - source range (start and end line/column)
  - the plain text message
  - the structured TaggedText form of the message (with subexpression refs)
  - the proof goal at that position, if any
  - the term-mode expected type at that position, if any
  - the enclosing declaration's name and range
  - a small source snippet around the error

The plain `lean --json` flag only gives you the first two-and-a-half
items. leanforge adds the rest — which is the data a human reads in
the InfoView when actually debugging a Lean file.


2. Install
----------

Prerequisites:

  - Lean toolchain via elan (https://lean-lang.org/lean4/doc/setup.html).
    The bundled example pins Lean 4.29.1 in
    examples/scratch/lean-toolchain; elan downloads it on first run.

  - uv (Python tool runner):
        brew install uv
    uv auto-provisions Python 3.12 and the `leanclient` package on
    demand. No virtualenv or pip steps are required.

That is the entire install.


3. How to run, and where to see the JSON
----------------------------------------

From the project root, against the bundled example:

    uv run --with leanclient --python 3.12 leanforge.py \
        examples/scratch Scratch/Basic.lean > out.json

First run takes ~10-30 seconds (Lean elaboration + dependency
fetch). Subsequent runs are ~2-3 seconds.

Outputs:

  - out.json                        whatever you redirect to
  - examples/sample_output.json     a committed reference output
                                    for the bundled example, so the
                                    schema is visible without running

Quick smoke test (verifies the LSP layer is alive):

    uv run --with leanclient --python 3.12 smoke_test.py

To run against your own Lean project, pass its Lake root and a file
path relative to that root:

    uv run --with leanclient --python 3.12 leanforge.py \
        /path/to/your/lake-project SomeModule/Foo.lean


JSON shape (per diagnostic)
---------------------------

    severity             "error" | "warning" | "information" | "hint"
    range                LSP range of the diagnostic
    fullRange            LSP fullRange (often equal to range)
    messageText          flat human-readable message
    messageInteractive   structured TaggedText tree
    goal                 tactic-mode goal at error pos, or null
    termGoal             term-mode expected type at error pos, or null
    enclosingDeclaration name + kind + range of surrounding decl
    sourceSnippet        +/- 3 lines around the error
    source, tags         pass-through from LSP

The top-level document also has: project root, file path, counts by
severity, an elaborationSucceeded flag, and a timedOut flag.


4. Possible next steps
----------------------

  - Flatten messageInteractive into a clean
        { expected, actual, expression }
    triple while the LSP RPC session is alive. The current raw
    TaggedText tree contains RpcRefs that become invalid once the
    session closes; resolving them up front makes the JSON
    self-contained.

  - Add hover info (type and docstring) for each identifier
    referenced inside the error range.

  - Surface get_code_actions output ("Try this" quick-fixes) so a
    downstream consumer can apply trivial fixes directly.

  - De-duplicate cascading errors when multiple diagnostics share
    the same root cause.

  - Add pyproject.toml so leanforge can be installed as a normal
    Python package instead of run via `uv run --with`.

  - Multi-file mode: today the CLI handles one file at a time.
