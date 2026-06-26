# 5 — Finalize the paper for submission

**Why only you:** judgment calls, an external artifact host/DOI, the target venue's
current CFP, and (if applicable) coordinated disclosure — none of which an offline
assistant can decide or perform for you.

Do these once the RQ8 numbers are real (Task 3 done).

## 5a. Swap in the camera-ready claims (only after measurement)
- [ ] Apply the rewrites in `Paper/Section/_rq8_camera_ready_edits.md` (abstract sentence,
      an intro contribution bullet, the Limitation (3) "we now measure it" version,
      conclusion line). **Do not apply these until the measured macros are populated**
      — until then the honest in-tree state is the protocol framing.
- [ ] Remove the `\providecommand{...}{[pending]}` block at the top of
      `Paper/Section/measured_evaluation.tex` once the generated macros are guaranteed present.

## 5b. Page budget
- [ ] The RQ8 section added ~3 pp (build is now 18 pp). Top venues (S&P/CCS/USENIX/NDSS)
      cap ~13 pp + refs. Condense: once RQ8 carries measured results, **absorb much of
      RQ7's prose** rather than keeping both, and tighten the protocol description.

## 5c. Pre-existing camera-ready checklist (from artifact/Paper/README.md)
- [ ] De-anonymize the author block in both wrappers: `Paper/IEEE/main.tex` (says `Paper #XXX`)
      and `Paper/ACM/main.tex` (acmart `[anonymous]` + `Anonymous Author(s)`).
- [ ] Host the artifact and add the anonymized review URL + the stable repo URL/DOI
      (e.g. Zenodo) for camera-ready. (Needs external hosting → only you.)
- [ ] Confirm the **target venue's current CFP**: page limit, ethics/open-science
      appendix requirements, artifact-evaluation track.

## 5d. Coordinated disclosure — only if triggered
- [ ] If the instrument returns **OPEN on a named, deployed system on a value-realizing
      path the attacker controls**, follow `Paper/Section/ethical_considerations.tex`: notify
      the affected project(s), embargo, and gate any exploit-enabling artifacts before
      publication. (The released artifact is the measurement harness, not a turnkey
      attack tool.) For the expected results — Cosmos RULED_OUT, the open window on a
      constructed control — no disclosure is triggered.

## 5e. Decide the venue
- [ ] Per the earlier assessment: with the measured result in hand, a top-4 security
      venue is in range; without it, Financial Cryptography (FC) / AFT are the strong
      fits. Pick the target and match formatting/limits.

---
Back to the [index](README.md).
