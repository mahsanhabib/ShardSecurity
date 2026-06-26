# Paper — *Priced to Equivocate*

This folder holds the paper. The body is written **once** in `Section/*.tex` and is
shared verbatim by two format wrappers, each in its own subfolder:

```
Paper/
├── Section/        the paper, section by section (abstract → appendices). EDIT HERE.
│   └── _generated/ tables/macros emitted by ../../artifact/make_tables.py (do not hand-edit)
├── IEEE/           IEEEtran build  →  IEEE/main.tex      (canonical)
├── ACM/            acmart build    →  ACM/main.tex
└── _legacy/        archived earlier wrappers (paper.tex, paper_article.tex, body.tex, …)
```

Only the preamble and front matter differ between `IEEE/main.tex` and `ACM/main.tex`;
both `\input{../Section/*.tex}`. The shared abstract routes its keyword line through a
`\paperkeywords` macro that each wrapper defines (IEEEtran → a bold inline line;
acmart → `\keywords{...}` before `\maketitle`).

## Build

```bash
# IEEE (canonical)
cd IEEE && pdflatex main && bibtex main && pdflatex main && pdflatex main

# ACM
cd ACM  && pdflatex main && bibtex main && pdflatex main && pdflatex main
```

Both resolve figures from `../../artifact/figures/` (via `\graphicspath`), the generated
data tables from `../Section/_generated/`, and the bibliography from `../../reference.bib`.

## Regenerating the data tables/figures

Numbers, figures, and the `_generated/` tables come from the artifact and must not be
hand-edited (re-running the pipeline rewrites them):

```bash
cd ../artifact
python run_all.py     --config configs/main.yaml
python plot_figures.py --input results/main.json --out figures/
python make_tables.py  --input results/main.json --out ../Paper/Section/_generated
```

## Notes

- `ACM/main.tex` uses the `[nonacm]` option so it compiles cleanly without a venue/DOI;
  for a real ACM submission, drop `nonacm` and add `\acmConference` / `\acmDOI` / CCS concepts.
- Both wrappers are anonymized for double-blind review (IEEEtran author block /
  acmart `[anonymous]`); de-anonymize at camera-ready.
- The RQ8 live-measurement runbook lives in `../artifact/MEASUREMENT.md`.
