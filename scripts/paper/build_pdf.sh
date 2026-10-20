#!/usr/bin/env bash
# Build paper/main.pdf from paper/main.tex.
#
# Passes: pdflatex, bibtex, pdflatex, pdflatex. The extra passes are needed
# for natbib to resolve the citations and for the cross-references to the
# generated tables and figures to settle.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
if ! command -v pdflatex >/dev/null 2>&1; then
  echo "pdflatex is required (TeX Live). Install texlive-latex-base and texlive-latex-recommended." >&2
  exit 1
fi
pdflatex -interaction=nonstopmode -halt-on-error -output-directory paper paper/main.tex
if command -v bibtex >/dev/null 2>&1; then
  bibtex paper/main || true
fi
pdflatex -interaction=nonstopmode -halt-on-error -output-directory paper paper/main.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory paper paper/main.tex
echo "Wrote paper/main.pdf"
