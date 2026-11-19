"""Fixture analysis for the evidence-provider tests.

A real ``@session`` run: clew records ``data/<input>`` as its input and
``results/<output>`` as its output, so claims on the output carry a recorded
lineage that ``clew verify --strict`` walks and the slice returns.

Usage: python scripts/compute.py --src <input.csv> --dst <output.json>
"""

import scitex_io as sio
from scitex_session import session


@session(verbose=False)
def main(src="data/input.csv", dst="results/results.json"):
    df = sio.load(src)
    results = {
        "auc": 0.91,
        "n_rows": len(df),
        "sum_x": int(df["x"].sum()),
    }
    sio.save(results, dst)
    return 0


if __name__ == "__main__":
    main()
