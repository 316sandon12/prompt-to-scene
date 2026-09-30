# Contributing

Start with the CLI crate example and the asset contract. Keep changes focused on the complete build/import/verify/revise workflow.

For a bug report include OS, Blender/Unity versions, render pipeline, a minimal non-sensitive modeling script, and the relevant receipt/error. Do not upload proprietary project assets or credentials.

Before a pull request run `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .`. Changes to the exporter/importer should include a real-engine reproduction when possible. State exactly which engines you ran; do not mark unrun engine checks as passed.

Keep the core transport independent of any particular LLM provider. New material features must specify validation, import mapping, revision behavior and an example. UE support should be a separate adapter using the same request/receipt semantics.
