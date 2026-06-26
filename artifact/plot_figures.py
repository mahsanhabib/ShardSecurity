#!/usr/bin/env python3
"""Regenerate every figure in the paper from results/main.json.

Usage:
    python plot_figures.py --input results/main.json --out figures/

Produces (all vector PDF):
    fig1_attack_flow.pdf      attack flow (committee reveal -> ... -> settlement)
    fig2_quorum.pdf           two 2F+1 quorums in a 3F+1 committee, F+1 overlap
    fig3_phase.pdf            profit phase diagram over (rho, V) + immunity note
    fig4_cost.pdf             bribe cost vs committee size for several q
    fig5_reconf_fsm.pdf       reconfiguration handoff state machine (safe/unsafe)
    fig6_reconf_profit.pdf    E[Pi(a)] over attack time within the epoch
    fig_pwin.pdf              RQ1: pwin vs latency ratio rho (+ immunity baseline)
    fig_psucc.pdf             floor: psucc vs view-split (closed form + MC)
    fig_profit_qV.pdf         RQ3: profit heatmap over (q, V)
    fig_defenses.pdf          RQ5: effect of each defense on E[Pi]

The diagram figures (1, 2, 5) are drawn programmatically so the whole figure
set is reproducible from this one script with no manual asset editing.
"""
from __future__ import annotations

import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Ellipse

plt.rcParams.update({
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "legend.fontsize": 7,
    "figure.dpi": 150,
    "savefig.bbox": "tight",
    "pdf.fonttype": 42,           # editable text in the PDF
    "ps.fonttype": 42,
})

COL = 3.35      # single-column width (inches)
C_PROFIT = "#1b7837"
C_LOSS = "#762a83"
C_NEUTRAL = "#4d4d4d"


# --------------------------------------------------------------------------
# helpers for the hand-drawn diagrams
# --------------------------------------------------------------------------
def _box(ax, x, y, w, h, text, fc="#eef3fb", ec="#34568b", fs=7):
    b = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                       linewidth=1.0, edgecolor=ec, facecolor=fc, zorder=2)
    ax.add_patch(b)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, zorder=3, wrap=True)
    return (x + w / 2, y + h / 2)


def _arrow(ax, p0, p1, color="#333333", style="-|>", rad=0.0, lw=1.1):
    a = FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=10,
                        connectionstyle=f"arc3,rad={rad}", color=color,
                        linewidth=lw, zorder=1)
    ax.add_patch(a)


# --------------------------------------------------------------------------
# Figure 1 : attack flow
# --------------------------------------------------------------------------
def fig_attack_flow(out):
    fig, ax = plt.subplots(figsize=(COL, 4.0))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    steps = [
        ("Committee revealed (epoch $e$)", False),
        ("Post conditional bribe (PayToEquivocate)", True),
        ("Bribe $F{+}1$ validators to equivocate", True),
        ("Engineer view split (leader equiv. / async)", True),
        ("Conflicting certs $\\sigma_A,\\sigma_B$ finalize", False),
        ("Cross-shard / bridge withdrawal (branch $A$)", False),
    ]
    n = len(steps)
    bw, bh = 0.80, 0.082
    top = 0.97
    vstep = 0.140
    xc = 0.10
    ys = [top - bh - i * vstep for i in range(n)]
    centers = []
    for i, ((s, adv), y) in enumerate(zip(steps, ys)):
        fc = "#fdecea" if adv else "#eef3fb"
        ec = "#b03a2e" if adv else "#34568b"
        centers.append(_box(ax, xc, y, bw, bh, s, fc=fc, ec=ec, fs=6.4))
    for i in range(n - 1):
        _arrow(ax, (xc + bw / 2, ys[i]), (xc + bw / 2, ys[i + 1] + bh))
    # accountability-race footer
    fy = ys[-1] - 0.085
    _box(ax, xc, fy, 0.385, 0.075, "value settles\nat $T_{\\mathrm{settle}}$",
         fc="#eafaf1", ec=C_PROFIT, fs=6.2)
    _box(ax, xc + 0.415, fy, 0.385, 0.075,
         "evidence enforced\nslash/revert at $T_{\\mathrm{acc}}$",
         fc="#f3e9f5", ec=C_LOSS, fs=6.2)
    _arrow(ax, (xc + 0.30, ys[-1]), (xc + 0.19, fy + 0.075), color=C_PROFIT)
    _arrow(ax, (xc + 0.50, ys[-1]), (xc + 0.61, fy + 0.075), color=C_LOSS)
    ax.text(0.5, fy - 0.045,
            "adversary keeps $V$ iff $T_{\\mathrm{settle}} < T_{\\mathrm{acc}}$",
            ha="center", va="center", fontsize=7.2, style="italic")
    fig.savefig(os.path.join(out, "fig1_attack_flow.pdf"))
    plt.close(fig)


# --------------------------------------------------------------------------
# Figure 2 : quorum intersection
# --------------------------------------------------------------------------
def fig_quorum(out):
    # N = 7 -> F = 2, Q = 5, F+1 = 3
    fig, ax = plt.subplots(figsize=(COL, 1.95))
    ax.set_xlim(-0.5, 7.0); ax.set_ylim(-1.1, 1.5); ax.axis("off")
    N, F = 7, 2
    Q = 2 * F + 1
    xs = np.arange(N)
    q1 = set(range(0, Q))           # {0,1,2,3,4}
    q2 = set(range(N - Q, N))       # {2,3,4,5,6}
    overlap = q1 & q2               # {2,3,4} -> F+1 = 3
    # quorum hulls
    ax.add_patch(Ellipse((np.mean(list(q1)), 0.0), Q + 0.9, 1.15, fill=True,
                         facecolor="#cfe0f3", edgecolor="#34568b", lw=1.2,
                         alpha=0.55, zorder=1))
    ax.add_patch(Ellipse((np.mean(list(q2)), 0.0), Q + 0.9, 1.15, fill=True,
                         facecolor="#f3d9cf", edgecolor="#b03a2e", lw=1.2,
                         alpha=0.55, zorder=1))
    for i in xs:
        eq = i in overlap
        ax.scatter([i], [0], s=240, zorder=3,
                   color="#b03a2e" if eq else "#f7f7f7",
                   edgecolor="#222222", linewidth=1.0)
        ax.text(i, 0, str(i + 1), ha="center", va="center", zorder=4,
                fontsize=7, color="white" if eq else "black")
    ax.text(np.mean(list(q1)), 0.78, "$Q_1$ ($2F{+}1$)", ha="center",
            color="#34568b", fontsize=8)
    ax.text(np.mean(list(q2)), -0.82, "$Q_2$ ($2F{+}1$)", ha="center",
            color="#b03a2e", fontsize=8)
    ax.annotate("$|Q_1\\cap Q_2|\\geq F{+}1$ must equivocate",
                xy=(3, 0.0), xytext=(3, 1.28), ha="center", fontsize=7.5,
                arrowprops=dict(arrowstyle="-|>", color="#222222", lw=1.0))
    ax.set_title("$N=3F{+}1=7$,   $Q=2F{+}1=5$,   floor $F{+}1=3$",
                 fontsize=8)
    fig.savefig(os.path.join(out, "fig2_quorum.pdf"))
    plt.close(fig)


# --------------------------------------------------------------------------
# Figure 3 : profit phase diagram over (rho, V)
# --------------------------------------------------------------------------
def fig_phase(res, out):
    d = res["rq3"]
    rho = np.array(d["rho"]); V = np.array(d["V"])
    Z = np.array(d["profit_rho_V"])
    fig, ax = plt.subplots(figsize=(COL, 2.7))
    vmax = np.nanmax(np.abs(Z))
    pc = ax.pcolormesh(rho, V, Z, cmap="PRGn", vmin=-vmax, vmax=vmax,
                       shading="auto")
    cs = ax.contour(rho, V, Z, levels=[0.0], colors="black", linewidths=1.3)
    ax.clabel(cs, fmt={0.0: "$E[\\Pi]=0$"}, fontsize=6)
    ax.axvline(1.0, color="#555555", ls="--", lw=0.9)
    ax.text(1.03, V.max() * 0.93, "$\\rho=1$", fontsize=6.5, color="#555555")
    ax.text(3.0, V.max() * 0.6, "profitable", ha="center", fontsize=7,
            color=C_PROFIT)
    ax.text(0.6, V.max() * 0.6, "window\nclosed", ha="center", fontsize=7,
            color=C_LOSS)
    ax.set_xlabel("latency ratio $\\rho=T_{\\mathrm{acc}}/T_{\\mathrm{settle}}$")
    ax.set_ylabel("extractable value $V$ (units of $s$)")
    ax.set_title(f"$E[\\Pi]$ over $(\\rho,V)$  ($N={d['N']}$, $q={d['q']}$, "
                 f"$p_{{\\mathrm{{succ}}}}={d['psucc']}$)")
    cb = fig.colorbar(pc, ax=ax, pad=0.02)
    cb.set_label("$E[\\Pi]$", fontsize=7)
    ax.text(0.02, -0.32, "Immunity baseline (finality-gated, $p_{\\mathrm{win}}=0$): "
            "$E[\\Pi]=-B-C_{\\mathrm{op}}<0$ everywhere.",
            transform=ax.transAxes, fontsize=6.2, style="italic")
    fig.savefig(os.path.join(out, "fig3_phase.pdf"))
    plt.close(fig)


# --------------------------------------------------------------------------
# Figure 4 : bribe cost vs committee size
# --------------------------------------------------------------------------
def fig_cost(res, out):
    d = res["rq2"]
    N = np.array(d["N"])
    fig, ax = plt.subplots(figsize=(COL, 2.4))
    markers = ["o", "s", "^", "D"]
    for (label, ys), m in zip(sorted(d["curves"].items()), markers):
        ax.plot(N, ys, marker=m, ms=3.5, lw=1.1, label=f"${label}$")
    ax.set_xlabel("committee size $N=3F{+}1$")
    ax.set_ylabel("min. total bribe $B=(F{+}1)q(s{+}R)$")
    ax.set_title(f"Bribe cost is linear in $N$ ($R={d['R']}s$)")
    ax.grid(True, alpha=0.3)
    ax.legend(title="enforcement $q$", ncol=2)
    fig.savefig(os.path.join(out, "fig4_cost.pdf"))
    plt.close(fig)


# --------------------------------------------------------------------------
# Figure 5 : reconfiguration handoff state machine
# --------------------------------------------------------------------------
def fig_reconf_fsm(out):
    fig, ax = plt.subplots(figsize=(COL, 2.9))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    # top row: epoch e -> drain -> boundary/handoff
    _box(ax, 0.02, 0.70, 0.29, 0.18, "Epoch $e$\nnormal phase", fs=6.6)
    _box(ax, 0.355, 0.70, 0.27, 0.18, "closing /\ndrain phase", fs=6.6)
    _box(ax, 0.675, 0.70, 0.30, 0.18, "boundary +\nstate/receipt\nhandoff", fs=6.2)
    # middle: epoch e+1 import
    _box(ax, 0.35, 0.44, 0.30, 0.16, "epoch $e{+}1$\nimport artifacts", fs=6.6)
    # bottom outcome boxes (taller, 2 lines)
    _box(ax, 0.02, 0.06, 0.45, 0.22,
         "execute receipt now\nvalue settles\n($T_{\\mathrm{settle}}<T_{\\mathrm{acc}}$: wins)",
         fc="#fdecea", ec="#b03a2e", fs=6.0)
    _box(ax, 0.53, 0.06, 0.45, 0.22,
         "hold for evidence window\nquarantine on conflict\n($T_{\\mathrm{settle}}\\geq T_{\\mathrm{acc}}$: $p_{\\mathrm{win}}{=}0$)",
         fc="#eafaf1", ec="#1b7837", fs=6.0)
    # arrows
    _arrow(ax, (0.31, 0.79), (0.355, 0.79))
    _arrow(ax, (0.625, 0.79), (0.675, 0.79))
    _arrow(ax, (0.80, 0.70), (0.58, 0.60), rad=-0.2)
    _arrow(ax, (0.44, 0.44), (0.28, 0.28), color="#b03a2e", rad=0.12)
    _arrow(ax, (0.56, 0.44), (0.72, 0.28), color="#1b7837", rad=-0.12)
    ax.text(0.275, 0.375, "ungated\n(unsafe)", color="#b03a2e", fontsize=6.2,
            ha="center", va="center")
    ax.text(0.725, 0.375, "gated\n(safe)", color="#1b7837", fontsize=6.2,
            ha="center", va="center")
    fig.savefig(os.path.join(out, "fig5_reconf_fsm.pdf"))
    plt.close(fig)


# --------------------------------------------------------------------------
# Figure 6 : E[Pi(a)] over attack time within the epoch
# --------------------------------------------------------------------------
def fig_reconf_profit(res, out):
    d = res["rq4"]["designs"]
    fig, ax = plt.subplots(figsize=(COL, 2.6))
    labels = {
        "hard_cutoff": ("A: hard cutoff", "#1f78b4", "-"),
        "unsafe_carryover": ("C: unsafe receipt carryover", "#e31a1c", "-"),
        "gated_carryover": ("accountability-gated carryover", "#33a02c", "-"),
        "reconfig_delay": ("reconfiguration delay $H_{\\mathrm{reconf}}$", "#ff7f00", "--"),
        "rolling": ("F: rolling reconfiguration", "#6a3d9a", "-."),
    }
    for key, (lab, col, ls) in labels.items():
        dd = d[key]
        ax.plot(dd["a_over_tau"], dd["profit"], color=col, ls=ls, lw=1.3,
                label=lab)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("attack time within epoch  $a/\\tau$")
    ax.set_ylabel("$E[\\Pi(a)]$")
    ax.set_title("Reconfiguration relocates the race")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="center left", fontsize=6.0)
    fig.savefig(os.path.join(out, "fig6_reconf_profit.pdf"))
    plt.close(fig)


# --------------------------------------------------------------------------
# RQ1 supporting : pwin vs rho
# --------------------------------------------------------------------------
def fig_pwin(res, out):
    d = res["rq1"]
    rho = np.array(d["rho"])
    fig, ax = plt.subplots(figsize=(COL, 2.3))
    for label, ys in sorted(d["curves"].items()):
        ax.plot(rho, ys, lw=1.3, label=f"settle CV {label.split('=')[1]}")
    ax.plot(rho, d["gated"], lw=1.3, color="#1b7837", ls="--",
            label="finality-gated (immune)")
    ax.axvline(1.0, color="#555555", ls=":", lw=0.9)
    ax.text(1.05, 0.1, "$\\rho=1$", fontsize=6.5, color="#555555")
    ax.set_xlabel("latency ratio $\\rho=T_{\\mathrm{acc}}/T_{\\mathrm{settle}}$")
    ax.set_ylabel("$p_{\\mathrm{win}}=\\Pr[T_{\\mathrm{settle}}<T_{\\mathrm{acc}}]$")
    ax.set_title("Window-open probability has a threshold at $\\rho=1$")
    ax.grid(True, alpha=0.3); ax.legend()
    fig.savefig(os.path.join(out, "fig_pwin.pdf"))
    plt.close(fig)


# --------------------------------------------------------------------------
# Floor supporting : psucc vs view-split
# --------------------------------------------------------------------------
def fig_psucc(res, out):
    d = res["floor"]
    phi = np.array(d["phi"])
    mc_phis = d["mc_phis"]
    mc_curves = d.get("mc_curves", {})
    fig, ax = plt.subplots(figsize=(COL, 2.3))
    mc_labelled = False
    for label, ys in sorted(d["curves"].items()):
        line, = ax.plot(phi, ys, lw=1.3, label=f"${label}$")
        # Monte-Carlo overlay on EVERY curve (not only the floor): the harness
        # enforces the quorum rule, so it tracks the closed form for k > F+1 too.
        if label in mc_curves:
            ax.scatter(mc_phis, mc_curves[label], color=line.get_color(),
                       edgecolors="black", linewidths=0.5, zorder=5, s=20,
                       marker="o", label="Monte-Carlo" if not mc_labelled else None)
            mc_labelled = True
    ax.axvline(0.5, color="#555555", ls=":", lw=0.9)
    ax.set_xlabel("view-split $\\varphi$ (fraction of honest votes on branch $A$)")
    ax.set_ylabel("$p_{\\mathrm{succ}}$")
    ax.set_title(f"Floor is necessary, not sufficient ($N={d['N']}$)")
    ax.grid(True, alpha=0.3); ax.legend()
    fig.savefig(os.path.join(out, "fig_psucc.pdf"))
    plt.close(fig)


# --------------------------------------------------------------------------
# RQ3 supporting : profit heatmap over (q, V)
# --------------------------------------------------------------------------
def fig_profit_qV(res, out):
    d = res["rq3"]
    q = np.array(d["q_grid"]); V = np.array(d["V"])
    Z = np.array(d["profit_q_V"])
    fig, ax = plt.subplots(figsize=(COL, 2.5))
    vmax = np.nanmax(np.abs(Z))
    pc = ax.pcolormesh(q, V, Z, cmap="PRGn", vmin=-vmax, vmax=vmax,
                       shading="auto")
    cs = ax.contour(q, V, Z, levels=[0.0], colors="black", linewidths=1.2)
    ax.clabel(cs, fmt={0.0: "$E[\\Pi]=0$"}, fontsize=6)
    ax.set_xlabel("enforcement probability $q$")
    ax.set_ylabel("extractable value $V$ (units of $s$)")
    ax.set_title(f"Profit over $(q,V)$ at $\\rho={d['rho_fixed']}$ "
                 f"($p_{{\\mathrm{{win}}}}={d['pwin_fixed']:.2f}$)")
    cb = fig.colorbar(pc, ax=ax, pad=0.02); cb.set_label("$E[\\Pi]$", fontsize=7)
    fig.savefig(os.path.join(out, "fig_profit_qV.pdf"))
    plt.close(fig)


# --------------------------------------------------------------------------
# RQ5 supporting : defenses
# --------------------------------------------------------------------------
def fig_defenses(res, out):
    rows = res["rq5"]["rows"]
    names = [r["defense"] for r in rows]
    profit = [r["profit"] for r in rows]
    colors = [C_PROFIT if p > 0 else C_LOSS for p in profit]
    fig, ax = plt.subplots(figsize=(COL, 2.5))
    y = np.arange(len(names))[::-1]
    ax.barh(y, profit, color=colors, alpha=0.85)
    ax.axvline(0, color="black", lw=0.9)
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=6.5)
    ax.set_xlabel("$E[\\Pi]$ after applying the lever")
    ax.set_title("Only levers that hit $p_{\\mathrm{win}}$ close the attack")
    for yi, p in zip(y, profit):
        ax.text(p + (1.5 if p >= 0 else -1.5), yi, f"{p:.1f}",
                va="center", ha="left" if p >= 0 else "right", fontsize=6)
    ax.margins(x=0.18)
    fig.savefig(os.path.join(out, "fig_defenses.pdf"))
    plt.close(fig)


# --------------------------------------------------------------------------
# RQ6 : testbed-measured pwin vs the closed form
# --------------------------------------------------------------------------
def fig_testbed(res, out):
    d = res["rq6"]
    rho = np.array(d["rho_measured"])
    order = np.argsort(rho)
    rho = rho[order]
    meas = np.array(d["pwin_measured"])[order]
    ana = np.array(d["pwin_analytic"])[order]
    fig, ax = plt.subplots(figsize=(COL, 2.4))
    ax.plot(rho, ana, "-", color="#999999", lw=1.4, label="analytical model")
    ax.scatter(rho, meas, s=26, color="#1b7837", zorder=5,
               label="testbed (measured)")
    ax.axvline(1.0, color="#555555", ls=":", lw=0.9)
    ax.text(1.04, 0.08, "$\\rho=1$", fontsize=6.5, color="#555555")
    ax.set_xlabel("measured latency ratio $\\rho=T_{\\mathrm{acc}}/T_{\\mathrm{settle}}$")
    ax.set_ylabel("$p_{\\mathrm{win}}$")
    ax.set_title("Discrete-event testbed reproduces the threshold")
    ax.grid(True, alpha=0.3); ax.legend(loc="upper left")
    fig.savefig(os.path.join(out, "fig_testbed.pdf"))
    plt.close(fig)


# --------------------------------------------------------------------------
# RQ7 : real-systems exposure
# --------------------------------------------------------------------------
def fig_realsystems(res, out):
    rows = res["rq7"]["rows"]
    names = [r["name"] for r in rows]
    bev = [r["breakeven_V_stakes"] for r in rows]
    wcol = {"gated": "#1b7837", "open": "#b03a2e", "depends": "#ff7f00"}
    colors = [wcol.get(r["window"], "#777777") for r in rows]
    fig, ax = plt.subplots(figsize=(COL, 2.6))
    y = np.arange(len(names))[::-1]
    ax.barh(y, bev, color=colors, alpha=0.85)
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=7)
    ax.set_xlabel("break-even $V^{*}$ (multiples of one validator's stake)")
    ax.set_title("Break-even value at documented parameters")
    for yi, b in zip(y, bev):
        ax.text(b + max(bev) * 0.01, yi, f"{b:.0f}", va="center", fontsize=6)
    # window-status legend
    from matplotlib.patches import Patch
    leg = [Patch(color=wcol["gated"], label="settlement gated (G1 closed)"),
           Patch(color=wcol["depends"], label="window depends"),
           Patch(color=wcol["open"], label="window open")]
    ax.legend(handles=leg, fontsize=6, loc="lower right")
    ax.margins(x=0.12)
    fig.savefig(os.path.join(out, "fig_realsystems.pdf"))
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=os.path.join("results", "main.json"))
    ap.add_argument("--out", default="figures")
    args = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    inp = os.path.join(here, args.input)
    out = os.path.join(here, args.out)
    os.makedirs(out, exist_ok=True)
    with open(inp, "r", encoding="utf-8") as fh:
        res = json.load(fh)

    fig_attack_flow(out)
    fig_quorum(out)
    fig_phase(res, out)
    fig_cost(res, out)
    fig_reconf_fsm(out)
    fig_reconf_profit(res, out)
    fig_pwin(res, out)
    fig_psucc(res, out)
    fig_profit_qV(res, out)
    fig_defenses(res, out)
    fig_testbed(res, out)
    fig_realsystems(res, out)
    print(f"[plot_figures] wrote 12 figures to {out}")


if __name__ == "__main__":
    main()
