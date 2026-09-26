# Paper draft

SciFact-native technical paper. Four-way gold and the human study are future work.

Build tables and figures from artifacts:

```
PYTHONPATH=src python3 scripts/paper/make_tables.py
PYTHONPATH=src python3 scripts/paper/make_figures.py
```

Export the draft PDF (two `pdflatex` passes):

```
bash scripts/paper/build_pdf.sh
```

or

```
pdflatex -interaction=nonstopmode -halt-on-error -output-directory paper paper/main.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory paper paper/main.tex
```

Writes `paper/main.pdf`. Results paragraphs are filled after the frozen
held-out run. If V does not reduce false endorsement versus B2, the same
tables are reported as a negative result.
