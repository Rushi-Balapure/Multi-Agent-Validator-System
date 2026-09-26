#!/usr/bin/env bash
# Build paper/main.pdf from paper/main.tex (two pdflatex passes for refs).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
if ! command -v pdflatex >/dev/null 2>&1; then
  echo "pdflatex is required (TeX Live). Install texlive-latex-base and texlive-latex-recommended." >&2
  exit 1
fi
pdflatex -interaction=nonstopmode -halt-on-error -output-directory paper paper/main.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory paper paper/main.tex
echo "Wrote paper/main.pdf"
