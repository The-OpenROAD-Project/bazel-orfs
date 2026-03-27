"""Plot DRC violation convergence from detail routing log.

Parses the route log for per-iteration violation counts and generates
a convergence plot (iterations on X, violations on Y).

Usage:
    python3 scripts/plot_route_drc.py <route_log> [output.png]
"""
import re
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    print("matplotlib required", file=sys.stderr)
    sys.exit(1)


def parse_route_log(path):
    """Extract per-iteration violation counts from route log."""
    iterations = []
    current_iter = None

    with open(path) as f:
        for line in f:
            # Start of iteration
            m = re.search(r"Start (\d+)(?:st|nd|rd|th) optimization iteration", line)
            if m:
                current_iter = int(m.group(1))
                continue

            # Completion percentage with violations
            m = re.search(r"Completing (\d+)% with (\d+) violations", line)
            if m and current_iter is not None:
                pct = int(m.group(1))
                viols = int(m.group(2))
                iterations.append((current_iter, pct, viols))
                continue

            # Final violation count for iteration
            m = re.search(r"Number of violations\s*=\s*(\d+)", line)
            if m and current_iter is not None:
                viols = int(m.group(1))
                iterations.append((current_iter, 100, viols))

    return iterations


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <route_log> [output.png]")
        sys.exit(1)

    log_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "drc_convergence.png"

    data = parse_route_log(log_path)
    if not data:
        print(f"No iteration data found in {log_path}")
        sys.exit(1)

    # Get final violation count per iteration (100% or max %)
    iter_finals = {}
    for it, pct, viols in data:
        if it not in iter_finals or pct > iter_finals[it][0]:
            iter_finals[it] = (pct, viols)

    iters = sorted(iter_finals.keys())
    final_viols = [iter_finals[i][1] for i in iters]

    fig, ax = plt.subplots(figsize=(8, 5))

    # Main line: final violations per iteration
    ax.plot(iters, final_viols, 'o-', color='#ef4444', linewidth=2,
            markersize=8, label='Violations (end of iteration)')

    # Annotate each point
    for i, v in zip(iters, final_viols):
        ax.annotate(f'{v:,}', (i, v), textcoords="offset points",
                    xytext=(0, 12), ha='center', fontsize=9)

    ax.set_xlabel('Optimization Iteration', fontsize=12)
    ax.set_ylabel('DRC Violations', fontsize=12)
    ax.set_title('Detail Routing DRC Convergence', fontsize=14,
                 fontweight='bold')
    ax.set_xticks(iters)
    ax.grid(axis='y', alpha=0.3)
    ax.legend(fontsize=10)

    if final_viols[-1] == 0:
        ax.annotate('✓ Clean!', (iters[-1], 0),
                    textcoords="offset points", xytext=(20, 20),
                    fontsize=14, color='green', fontweight='bold')

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")
    print(f"Iterations: {len(iters)}, Final violations: {final_viols[-1]}")


if __name__ == "__main__":
    main()
