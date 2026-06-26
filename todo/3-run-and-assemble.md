# 3 — Run the measurement + fold it into the paper

**Why only you:** these commands hit your configured live endpoints from your
machine, and the final LaTeX compile runs locally.

Prereqs: Tasks 1 (and ideally 2) done; `rq8.endpoints` filled in.

## Steps (run from `artifact/`)
- [ ] Freeze the pre-registration **before** collecting (so the decision rule is
      committed in advance). This repo isn't git yet — initialize and tag:
      ```bash
      git init && git add -A && git commit -m "Pre-measurement snapshot"
      git tag prereg/rq8-v1
      ```
      Record the commit hash in `configs/main.yaml → rq8.preregistration.hash`.
- [ ] Dry-run to confirm which arms will run:
      ```bash
      python measure_all.py --dry-run
      ```
- [ ] Collect everything configured, then assemble into the paper:
      ```bash
      python measure_all.py --assemble
      ```
      (`--assemble` runs `run_all.py` + `make_tables.py`; it folds
      `results/measured/*.jsonl` into `results/main.json → rq8` and regenerates the
      measured macros + `tab_measured.tex`.)
- [ ] Regenerate figures and compile the paper:
      ```bash
      python plot_figures.py --input results/main.json --out figures/
      cd ../Paper/IEEE && pdflatex main && bibtex main && pdflatex main && pdflatex main
      ```

## Done when
- [ ] `results/main.json → rq8.paths` shows the verdicts
      (Cosmos **RULED_OUT**, bridge **OPEN** if paired, controls as expected).
- [ ] The RQ8 section in the compiled PDF shows **real numbers**, not `[pending]`.
- [ ] `Paper/Section/_generated/tab_measured.tex` exists with your measured rows.

## If something skips or errors
- An arm prints exactly what endpoint to set. Bridge schema mismatch → adjust
  `bridge.query`/keys (see Task 1b). Cosmos `block_search` disabled → pass
  `cosmos.heights` manually.

---
**Next:** [5-finalize-paper.md](5-finalize-paper.md) (and [4-optional-devnet.md](4-optional-devnet.md) for full rigor).
