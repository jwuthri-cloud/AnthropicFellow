"""Merge the Opus-reviewed scenario files into data/scenarios/pairs_v2.jsonl and validate them.

Reads every data/scenarios/reviewed/pairs_new_*.jsonl (not the *_review.jsonl logs), drops the
pair_ids listed in reviewed/merge_drops.txt, re-checks each pair against the spec, flags likely
duplicate situations across files (high word overlap between the two fact regions) and prints
counts by category, severity tier, fact distance and target letter.

    uv run python scripts/merge_scenarios.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "scenarios"
CATEGORIES = {
    "physical_injury": "life_body",
    "medical": "life_body",
    "child_vulnerable": "life_body",
    "third_party_physical": "life_body",
    "mass_public_safety": "life_body",
    "financial": "material",
    "legal_status": "material",
    "data_loss": "material",
    "privacy_security": "social_privacy",
    "social_psychological": "social_privacy",
}
SHARED = ("harm_type", "fact_distance", "system", "action")


def fact_region(harm: str, benign: str) -> tuple[str, str]:
    """The differing span of each user text, by common prefix and suffix."""
    i = 0
    while i < min(len(harm), len(benign)) and harm[i] == benign[i]:
        i += 1
    j = 0
    while j < min(len(harm), len(benign)) - i and harm[-1 - j] == benign[-1 - j]:
        j += 1
    return harm[i : len(harm) - j], benign[i : len(benign) - j]


def check_pair(harm: dict, benign: dict) -> list[str]:
    """Spec violations for one pair (empty when it passes)."""
    problems = [f"{k} differs" for k in SHARED if harm[k] != benign[k]]
    if harm["harm_type"] not in CATEGORIES:
        problems.append(f"unknown category {harm['harm_type']}")
    target = re.compile(harm["action"], re.IGNORECASE)
    hits = [x for x in "ABC" if target.search(f"ACTION: {x}")]
    if len(hits) != 1 or not target.search(f"ACTION: **{hits[0]}**"):
        problems.append(f"regex matches {hits}")
    h, b = fact_region(harm["user"], benign["user"])
    if "\n\n" in h or "\n\n" in b or re.search(r"\n[ABC]\) ", h + b):
        problems.append("fact region crosses a paragraph or the options")
    if abs(len(harm["user"]) - len(benign["user"])) > 0.1 * len(harm["user"]):
        problems.append("lengths differ by more than 10%")
    return problems


def main() -> None:
    drops = {
        line.split()[0]
        for line in (ROOT / "reviewed" / "merge_drops.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    rows, sources = [], {}
    for path in sorted((ROOT / "reviewed").glob("pairs_new_*.jsonl")):
        if path.stem.endswith("_review"):
            continue
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row["pair_id"] not in drops:
                rows.append(row)
                sources[row["pair_id"]] = path.stem
    by_pair: dict[str, dict] = {}
    for row in rows:
        by_pair.setdefault(row["pair_id"], {})[row["condition"]] = row
    assert len({r["id"] for r in rows}) == len(rows), "duplicate ids"
    bad = {p: check_pair(v["harm"], v["benign"]) for p, v in by_pair.items() if len(v) == 2}
    incomplete = [p for p, v in by_pair.items() if len(v) != 2]
    failing = {p: v for p, v in bad.items() if v}

    # Likely duplicate situations: shared content words between harm fact regions across files.
    def words(pid: str) -> set[str]:
        h, _ = fact_region(by_pair[pid]["harm"]["user"], by_pair[pid]["benign"]["user"])
        return {w for w in re.findall(r"[a-z]{4,}", h.lower())}

    vocab = {p: words(p) for p in by_pair if p not in failing and p not in incomplete}

    def jaccard(a: str, b: str) -> float:
        return len(vocab[a] & vocab[b]) / max(1, len(vocab[a] | vocab[b]))

    dupes = [
        (a, b, round(jaccard(a, b), 2))
        for a, b in combinations(sorted(vocab), 2)
        if sources[a] != sources[b] and jaccard(a, b) >= 0.4
    ]

    keep = [r for r in rows if r["pair_id"] not in failing and r["pair_id"] not in incomplete]
    for row in keep:
        row["tier"] = CATEGORIES[row["harm_type"]]
    out = ROOT / "pairs_v2.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep))

    harm_rows = [r for r in keep if r["condition"] == "harm"]
    print(
        f"pairs kept: {len(harm_rows)}  dropped by list: {len(drops)}"
        f"  failing checks: {len(failing)}  incomplete: {len(incomplete)}"
    )
    for pid, problems in failing.items():
        print("  FAIL", pid, sources.get(pid), problems)
    print("by category:", dict(Counter(r["harm_type"] for r in harm_rows).most_common()))
    print("by tier:", dict(Counter(r["tier"] for r in harm_rows)))
    print("near/far:", dict(Counter(r["fact_distance"] for r in harm_rows)))
    letters = Counter(
        next(x for x in "ABC" if re.search(r["action"], f"ACTION: {x}", re.IGNORECASE))
        for r in harm_rows
    )
    print("target letters:", dict(letters))
    print(f"possible duplicate situations across files (fact-word Jaccard >= 0.4): {len(dupes)}")
    for a, b, j in sorted(dupes, key=lambda x: -x[2])[:30]:
        print(f"  {a} ({sources[a]}) ~ {b} ({sources[b]})  J={j}")
    print("wrote", out)


if __name__ == "__main__":
    main()
