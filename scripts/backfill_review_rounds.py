#!/usr/bin/env python3
"""把历史 review 存档里声明的轮次回填进 model_review_runs.review_rounds。

只回填【轮次】——耗时(duration_seconds)历史上从没记过，不做任何推算，宁可留 NULL。

匹配方式：reviews/<owner>-<repo>-<pr>-<verdict>-<sha>-<date>.md 的文件名给出
owner/repo/pr/head_oid 前缀，用它去 model_review_runs 找同 PR 且 head_oid 以该
前缀开头的行；文件正文里的 "4-round" / "2-round" / "[4round]" 给出轮次。

一个 (pr, sha) 可能对应多次 run（同一 head 复审过多轮），这些行拿同一个轮次值是对的：
存档是那次 head 的最终结论。反过来，同一 PR 不同 sha 不会互相污染。

用法：
    python3 scripts/backfill_review_rounds.py            # 预演，只打印
    python3 scripts/backfill_review_rounds.py --apply    # 真写库
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEWS_DIR = ROOT / "reviews"
DEFAULT_DB = ROOT / "reviews" / "model-evals" / "model-evals.sqlite"

# jhfnetboy-CMIC-143-request-changes-f27b65f-2026-08-04.md
#   verdict 段自身含连字符，所以从两端锚定：前 2 段是 owner/repo？—— 不成立，repo 名也可能带连字符。
#   可靠的锚点是【第一个纯数字段】= PR 号，它左边是 owner-repo，右边是 verdict-sha-date。
NAME_RE = re.compile(r"^(?P<slug>.+?)-(?P<pr>\d+)-(?P<rest>.+)$")
SHA_RE = re.compile(r"-([0-9a-f]{7,40})-\d{4}-\d{2}-\d{2}$")
ROUNDS_RE = re.compile(r"\b(\d)\s*-?\s*round\b", re.IGNORECASE)


def parse_name(stem: str) -> tuple[str, int, str] | None:
    """→ (owner-repo slug, pr_number, head_sha_prefix)；解析不出来就 None（跳过，不猜）。"""
    m = NAME_RE.match(stem)
    if not m:
        return None
    sha_m = SHA_RE.search(m.group("rest"))
    if not sha_m:
        return None
    return m.group("slug"), int(m.group("pr")), sha_m.group(1)


def parse_rounds(text: str) -> int | None:
    """正文里声明的轮次；只认 2/4（v4 pipeline 的两条路径），别的一律不回填。"""
    for m in ROUNDS_RE.finditer(text):
        value = int(m.group(1))
        if value in (2, 4):
            return value
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--reviews-dir", default=str(REVIEWS_DIR))
    ap.add_argument("--apply", action="store_true", help="真写库（默认只预演）")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(model_review_runs)")}
    if "review_rounds" not in columns:
        print("review_rounds 列不存在——先跑一次 model_eval_db.py（connect() 会自动 ALTER）", file=sys.stderr)
        return 1

    matched = skipped_no_rounds = skipped_no_row = 0
    updates: list[tuple[int, int]] = []
    seen_runs: set[int] = set()

    for path in sorted(Path(args.reviews_dir).glob("*.md")):
        parsed = parse_name(path.stem)
        if not parsed:
            continue
        slug, pr_number, sha_prefix = parsed
        rounds = parse_rounds(path.read_text(encoding="utf-8", errors="replace"))
        if rounds is None:
            skipped_no_rounds += 1
            continue
        # slug = "owner-repo"，但 owner/repo 各自都可能含连字符 —— 别拆，直接用 owner||'-'||repo 比。
        rows = conn.execute(
            """
            SELECT id, owner, repo, head_oid FROM model_review_runs
            WHERE pr_number = ? AND owner || '-' || repo = ?
              AND head_oid IS NOT NULL AND head_oid LIKE ? || '%'
              AND review_rounds IS NULL
            """,
            (pr_number, slug, sha_prefix),
        ).fetchall()
        if not rows:
            skipped_no_row += 1
            continue
        for row in rows:
            if row["id"] in seen_runs:      # 同 run 已被别的存档认领 → 不覆盖，先到先得
                continue
            seen_runs.add(row["id"])
            updates.append((row["id"], rounds))
            matched += 1

    print(f"可回填 {matched} 行；存档无轮次声明 {skipped_no_rounds} 个；对不上 run 行 {skipped_no_row} 个")
    if not args.apply:
        for run_id, rounds in updates[:15]:
            print(f"  [预演] run#{run_id} → review_rounds={rounds}")
        if len(updates) > 15:
            print(f"  … 另 {len(updates) - 15} 行")
        print("加 --apply 才真写。")
        return 0

    with conn:
        conn.executemany("UPDATE model_review_runs SET review_rounds = ? WHERE id = ?",
                         [(r, i) for i, r in updates])
    print(f"已写入 {len(updates)} 行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
