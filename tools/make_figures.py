"""
논문용 데이터 기반 그림 생성 — Fig. 7(실험 환경), Fig. 8(실험 결과)만.

Fig. 7 : run_experiments.py 와 동일한 40x30 맵(벽/건물/빈/로봇/집하장)을 그대로 그린다.
Fig. 8 : tools/experiments_results.json 의 E2/E3/E4 수치를 그대로 plot 한다.

데이터를 임의로 만들지 않는다 — 맵은 코드, 수치는 실험 JSON에서 읽는다.

사용:
    source .venv/bin/activate
    python tools/run_experiments.py      # (먼저) 수치 생성
    python tools/make_figures.py         # → figures/fig7_environment.png, fig8_results.png
    python tools/build_manuscript.py     # 논문에 자동 삽입
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

# 논문 본문(Times New Roman)과 글꼴 통일
plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["mathtext.fontset"] = "stix"  # 수식($r_{infl}$)도 Times 계열로

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTDIR = os.path.join(ROOT, "figures")
os.makedirs(OUTDIR, exist_ok=True)

with open(os.path.join(HERE, "experiments_results.json")) as f:
    R = json.load(f)

# ---------- run_experiments.py 와 동일한 맵 정의 ----------
MAP_WIDTH, MAP_HEIGHT = 40, 30
COLLECTION_POINT = (20, 27)
BINS = {1: (11, 8), 2: (26, 8), 3: (11, 21), 4: (26, 21)}
ROBOT_START = {"A": (3, 26), "B": (36, 26)}
# (x1, y1, x2, y2, label)
BUILDINGS = [
    (4, 3, 9, 7, "Bldg"), (27, 3, 32, 7, "Bldg"),
    (4, 16, 9, 20, "Bldg"), (27, 16, 32, 20, "Bldg"),
    (16, 11, 21, 13, "Playground"),
    (14, 23, 23, 25, "Parking"),
    (19, 28, 20, 28, ""),
]


def fig7_environment():
    fig, ax = plt.subplots(figsize=(6.2, 4.7))
    ax.add_patch(Rectangle((0, 0), MAP_WIDTH, MAP_HEIGHT, fill=False,
                           edgecolor="black", lw=1.5))
    for (x1, y1, x2, y2, label) in BUILDINGS:
        w, h = (x2 - x1 + 1), (y2 - y1 + 1)
        ax.add_patch(Rectangle((x1, y1), w, h, facecolor="#9e9e9e",
                               edgecolor="#555555", lw=0.8))
        if label:
            ax.text(x1 + w / 2, y1 + h / 2, label, ha="center", va="center",
                    fontsize=6.5, color="white")
    for bid, (x, y) in BINS.items():
        ax.scatter(x, y, s=180, marker="s", color="#2e7d32",
                   edgecolor="black", zorder=5)
        ax.text(x, y, f"B{bid}", ha="center", va="center", fontsize=7,
                color="white", zorder=6)
    for name, (x, y) in ROBOT_START.items():
        ax.scatter(x, y, s=190, marker="^", color="#1565c0",
                   edgecolor="black", zorder=5)
        ax.text(x, y - 1.3, f"CS-{name}", ha="center", va="top", fontsize=7,
                color="#1565c0")
    cx, cy = COLLECTION_POINT
    ax.scatter(cx, cy, s=320, marker="*", color="#c62828",
               edgecolor="black", zorder=5)

    ax.set_xlim(-1, MAP_WIDTH + 1)
    ax.set_ylim(-1, MAP_HEIGHT + 1)
    ax.set_aspect("equal")
    ax.set_xlabel("x [cells]")
    ax.set_ylabel("y [cells]")
    ax.invert_yaxis()  # 격자 좌표계(상단이 y=0)와 일치
    ax.set_xticks(range(0, MAP_WIDTH + 1, 5))
    ax.set_yticks(range(0, MAP_HEIGHT + 1, 5))
    ax.grid(True, ls=":", lw=0.4, color="#cccccc")
    legend = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#2e7d32",
               markeredgecolor="black", markersize=9, label="Bin"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#1565c0",
               markeredgecolor="black", markersize=10, label="Robot start (CS)"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#c62828",
               markeredgecolor="black", markersize=13, label="Central depot"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#9e9e9e",
               markeredgecolor="#555", markersize=9, label="Building / obstacle"),
    ]
    ax.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.13),
              ncol=2, fontsize=7, frameon=False)
    fig.tight_layout()
    out = os.path.join(OUTDIR, "fig7_environment.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("saved:", out)


def fig8_results():
    E2, E3, E4 = R["E2_inflation"], R["E3_tsp_quality"], R["E4_scalability"]
    fig, axes = plt.subplots(3, 1, figsize=(4.2, 9.6))

    # (a) inflation trade-off : path len & A* time vs r_infl
    ax = axes[0]
    r = [x["inflation_radius"] for x in E2]
    plen = [x["total_path_len"] for x in E2]
    atime = [x["avg_astar_ms"] for x in E2]
    l1, = ax.plot(r, plen, "o-", color="#1565c0", label="Path length")
    ax.set_xlabel("Inflation radius  $r_{infl}$ [cells]")
    ax.set_ylabel("Total path length [cells]", color="#1565c0")
    ax.tick_params(axis="y", labelcolor="#1565c0")
    ax2 = ax.twinx()
    l2, = ax2.plot(r, atime, "s--", color="#c62828", label="A* query time")
    ax2.set_ylabel("A* query time [ms]", color="#c62828")
    ax2.tick_params(axis="y", labelcolor="#c62828")
    ax.set_xticks(r)
    ax.set_title("(a) Inflation-radius trade-off", fontsize=9)
    ax.legend(handles=[l1, l2], loc="upper left", fontsize=7, frameon=False)

    # (b) NN optimality gap vs N
    ax = axes[1]
    rnd = [x for x in E3 if x["case"] == "random"]
    N = [x["N"] for x in rnd]
    mean_gap = [x["mean_gap_pct"] for x in rnd]
    max_gap = [x["max_gap_pct"] for x in rnd]
    ax.plot(N, mean_gap, "o-", color="#2e7d32", label="Mean gap")
    ax.plot(N, max_gap, "^--", color="#9e9e9e", label="Max gap")
    real = next(x for x in E3 if x["case"] == "real_4bin")
    ax.scatter([real["N"]], [real["gap_pct"]], color="#c62828", zorder=5,
               marker="*", s=140, label="Real 4-bin layout")
    ax.set_xlabel("Number of bins  N")
    ax.set_ylabel("Optimality gap vs. optimal [%]")
    ax.set_xticks(N)
    ax.set_title("(b) Nearest-neighbor optimality gap", fontsize=9)
    ax.legend(loc="upper left", fontsize=7, frameon=False)

    # (c) scalability : query time vs grid cells
    ax = axes[2]
    cells = [x["cells"] for x in E4]
    qt = [x["avg_time_ms"] for x in E4]
    grids = [x["grid"] for x in E4]
    ax.plot(cells, qt, "o-", color="#6a1b9a")
    for cxx, cyy, g in zip(cells[:-1], qt[:-1], grids[:-1]):
        ax.annotate(g, (cxx, cyy), textcoords="offset points", xytext=(0, 7),
                    ha="center", fontsize=6.2, color="#555")
    ax.set_xlabel("Grid size [cells]")
    ax.set_ylabel("A* query time [ms]")
    ax.set_title("(c) Path-planning scalability", fontsize=9)

    fig.tight_layout()
    out = os.path.join(OUTDIR, "fig8_results.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("saved:", out)


if __name__ == "__main__":
    fig7_environment()
    fig8_results()
