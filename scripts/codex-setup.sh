#!/usr/bin/env bash
# Codex Cloud environment setup for swamikit/swami.
#
# The parser and codegen are Python stdlib only, so nothing to install for them.
# What we DO install: tree-sitter + tree-sitter-languages so the cloud agent can
# run the Swift syntax pre-gate against generated code (per CLAUDE.md verify gate).
#
# Paste this into the "Setup script" field of the Codex Cloud environment for this
# repo, or invoke it directly if the env picks up scripts by convention.

set -euo pipefail

echo "==> python: $(python3 --version)"

python3 -m pip install --upgrade pip --quiet

# tree-sitter (core Python binding) + tree-sitter-languages (bundles Swift grammar).
# If tree-sitter-languages ever breaks for you, the alternative is py-tree-sitter-languages.
python3 -m pip install --quiet tree-sitter tree-sitter-languages

echo "==> tree-sitter versions:"
python3 -c "import tree_sitter; print('  tree_sitter', tree_sitter.__version__)"
python3 -c "import tree_sitter_languages; print('  tree_sitter_languages OK')"

# Quick sanity check that the parser module actually imports (no accidental deps).
python3 -c "import importlib.util, pathlib
p = pathlib.Path('tool/src/parser/origami_graph.py')
assert p.exists(), 'parser missing at expected path'
spec = importlib.util.spec_from_file_location('origami_graph', p)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
print('  parser imports clean')"

echo "==> codex env ready."
