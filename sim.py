"""Hysteresis / dwell-time simulation for one road segment during a stadium crowd surge.

Supports Task 6 (oscillation test) and Task 7 (sensor outage) of the ED5012 midsem answer.
All data is synthetic: it illustrates the state-machine logic, not real-world performance.
Parameters and state machine match the submitted report (risk 0-100, 10 s cycle, Sec. 2.2).
"""
import numpy as np
import matplotlib.pyplot as plt

DT = 10                            # risk cycle, s
T_END = 7200                       # 17:30 -> 19:30
ENTER = [30, 50, 70]               # G->Y, Y->O, O->R
RELEASE = [20, 40, 60]             # Y->G, O->Y, R->O
RELEASE_DWELL = [180, 120, 120]    # s below release threshold, indexed by (level being left - 1)
OUTAGE = (1080, 1680)              # sensors blind during the crowd ramp-up
NOISE = 5.0                        # sensor noise, risk points
SIGMA0, SIGMA_GROWTH = 0.05, 0.0015  # uncertainty; grows per second of staleness
K_GOOD, K_POOR = 1.5, 2.0          # conservatism by coverage
NAMES = ["green", "yellow", "orange", "red"]


def level(x):
    return np.searchsorted(ENTER, x, side="right")


def scenario(seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(0, T_END, DT)
    truth = np.interp(t, [0, 900, 1800, 3600, 5400, 7200], [5, 5, 90, 90, 5, 5])
    meas = np.clip(truth + rng.normal(0, NOISE, t.size), 0, 100)
    blind = (t >= OUTAGE[0]) & (t < OUTAGE[1])
    mu, age = meas.copy(), np.zeros(t.size)
    for i in range(1, t.size):
        if blind[i]:                               # stale: last reading held, system doesn't know the truth
            mu[i], age[i] = mu[i - 1], age[i - 1] + DT
    sigma = SIGMA0 + SIGMA_GROWTH * age
    rc = 100 * np.minimum(1, mu / 100 + np.where(blind, K_POOR, K_GOOD) * sigma)
    return t, truth, mu, rc, blind


def designed(rc):
    """Report Sec. 2.2: two-cycle persistence to escalate, separate release thresholds, release dwell."""
    s, below, prev_target, out = 0, 0, 0, []
    for r in rc:
        target = level(r)
        if min(target, prev_target) > s:
            s, below = min(target, prev_target), 0
        elif s > 0 and r < RELEASE[s - 1]:
            below += DT
            if below >= RELEASE_DWELL[s - 1]:
                s, below = s - 1, 0
        else:
            below = 0
        prev_target = target
        out.append(s)
    return np.array(out)


def metrics(state, truth):
    changes = np.flatnonzero(np.diff(state)) + 1
    dirs = np.sign(state[changes] - state[changes - 1])
    rev = changes[1:][dirs[1:] != dirs[:-1]]                      # direction reversals (report Sec. 6.2)
    win = max((((rev >= i) & (rev < i + 300 // DT)).sum() for i in range(len(state))), default=0)
    red, hot = np.flatnonzero(state == 3), np.flatnonzero(truth >= ENTER[2])
    return {
        "flips": len(changes),
        "reversals/5min": int(win),
        "unsafe exposure (s)": int(((truth >= ENTER[2]) & (state < 3)).sum() * DT),
        "over-restriction (s)": int(((state >= 2) & (truth < ENTER[1] - 10)).sum() * DT),
        "red lag (s)": int((red[0] - hot[0]) * DT),
    }


def main():
    t, truth, mu, rc, blind = scenario()
    runs = {
        "naive (mu, single threshold)": level(mu),
        "conservative, memoryless": level(rc),
        "designed (hysteresis+dwell)": designed(rc),
    }
    res = {n: metrics(s, truth) for n, s in runs.items()}

    cols = list(next(iter(res.values())))
    print(f"{'policy':32}" + "".join(f"{c:>22}" for c in cols))
    for n, m in res.items():
        print(f"{n:32}" + "".join(f"{m[c]:>22}" for c in cols))
    print("(red lag < 0 means red was set before the true risk crossed 70; over-restriction = orange/red while true risk < 40)")

    naive, memless, des = (res[n] for n in res)
    assert des["flips"] < memless["flips"] and des["flips"] < naive["flips"]
    assert des["reversals/5min"] <= 1 < memless["reversals/5min"]      # report Sec. 6.2 acceptance criterion
    assert des["unsafe exposure (s)"] < naive["unsafe exposure (s)"]

    fig, ax = plt.subplots(4, 1, figsize=(10, 9), sharex=True)
    h = t / 3600 + 17.5
    ax[0].plot(h, truth, "k", label="true risk")
    ax[0].plot(h, mu, lw=.6, c="tab:blue", label="measured mu (held when blind)")
    ax[0].plot(h, rc, lw=.8, c="tab:red", label="conservative R^c")
    for v in ENTER:
        ax[0].axhline(v, ls=":", c="gray", lw=.6)
    ax[0].legend(fontsize=7, loc="upper right")
    ax[0].set_ylabel("risk")
    for a, (n, s) in zip(ax[1:], runs.items()):
        a.step(h, s, where="post")
        a.set_yticks(range(4), NAMES, fontsize=7)
        a.set_title(f"{n}: {res[n]['flips']} flips", fontsize=8, loc="left")
    for a in ax:
        a.axvspan(OUTAGE[0] / 3600 + 17.5, OUTAGE[1] / 3600 + 17.5, color="orange", alpha=.15)
    ax[-1].set_xlabel("time of day (h); shaded = sensor outage")
    fig.tight_layout()
    fig.savefig("results.png", dpi=130)


if __name__ == "__main__":
    main()
