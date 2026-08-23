#!/usr/bin/env python3
"""selfcheck_review.py — 自评块里的事实字段，从产物里读出来，而不是凭回忆写。

    python3 scripts/selfcheck_review.py --repo OWNER/REPO --pr N [--since ISO8601]

为什么要有这个东西
------------------
自评块问的是「你这轮做了什么」，而我是**凭回忆**回答的。2026-08-19 那一晚同一个
根的错踩了五次（「我以为做了 A，实际做了 B」），五次**全都写进了自评块**还是错的：
把答案喂进去验证还标成最高性价比、没打开那个 99KB 的 raw 就断言 codex 挂起、
手写 cron prompt 造了第四份范围源、把单轮标成 4-round……所以再加一条「要如实」的
自然语言约束是零收益的 —— 那正是已经存在并且已经失效的那份东西。

这个脚本只干一件事：**对每个断言去找它本该留下的产物**。找到了就把产物里的事实
原样打出来；找不到就打 `⚠️ 无产物` —— 那本身就是一条发现，比一句流畅的回忆值钱。

它不判断 review 的好坏，也不碰任何审查逻辑。它只回答「这件事到底留没留下痕迹」。
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PR_DAEMON = Path(__file__).resolve().parent.parent
EVAL_DB = PR_DAEMON / "reviews" / "model-evals" / "model-evals.sqlite"

OK = "✅"
MISSING = "⚠️ 无产物"
MISMATCH = "❌ 对不上"


def _fmt_age(mtime: float) -> str:
    delta = time.time() - mtime
    if delta < 90:
        return f"{delta:.0f}s 前"
    if delta < 5400:
        return f"{delta / 60:.0f}min 前"
    return f"{delta / 3600:.1f}h 前"


def _parse_since(raw):
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.astimezone()
    return ts.timestamp()


class Artifact:
    """一个断言 + 它本该留下的文件。"""

    def __init__(self, label, path, since=None):
        self.label = label
        self.path = Path(path) if path else None
        self.since = since

    @property
    def exists(self):
        return bool(self.path and self.path.is_file())

    def line(self, extra=""):
        if not self.exists:
            return f"  {MISSING}  {self.label}  (期望在 {self.path})"
        st = self.path.stat()
        stale = ""
        if self.since and st.st_mtime < self.since:
            stale = f"  {MISMATCH} 早于本轮起点 —— 这是**上一轮**留下的文件"
        return (
            f"  {OK}  {self.label}  {st.st_size}B  {_fmt_age(st.st_mtime)}"
            f"{('  ' + extra) if extra else ''}{stale}"
        )


def count_findings(path: Path) -> str:
    """数一数 R1 产出里真正的 finding 行，并认出两种已知的退化形态。"""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    # 允许行首有列表记号（`- ` / `* ` / `1. ` / `F3 `）—— DeepSeek 两种模式的输出
    # 形态不一样：R1a 直接 `[Low] file:line`，R1b 是 `1. [High] file:line`。
    # 只认行首裸中括号会把 R1b 数成 0 条，而「0 条」读起来正好像「它判 clean」。
    lead = r"^[ \t]*(?:[-*+]\s+|\d+[.)]\s+|F\d+\s+)?"
    findings = re.findall(lead + r"\[(Critical|High|Medium|Low|Info)\]", text, re.M | re.I)
    notes = [f"{len(findings)} 条 finding"]
    # 退化形态①：同一条 finding 以两个严重度报两遍
    bodies = re.findall(lead + r"\[[A-Za-z]+\]\s*(.+)$", text, re.M)
    trimmed = [b.strip()[:60] for b in bodies]
    if len(trimmed) != len(set(trimmed)):
        notes.append("⚠️ 有重复正文(同一条报了两个严重度?)")
    # 退化形态②：自我否定，推理当成 finding 发出来了
    if findings and re.search(r"no issue|not an issue|实际没有问题", text, re.I):
        notes.append("⚠️ 正文里出现「No issue」自我否定")
    if not findings and re.search(r"\bnone\b|无\s*(安全)?问题|clean", text, re.I):
        notes.append("(明确判 clean)")
    return " · ".join(notes)


def read_challenger(out_file: Path) -> str:
    """R3 的挑战者身份，从 codex_pk.sh 的 stdout 第一行**原样读出来**。

    ROADMAP 5.3 挂着的那条 TODO：这一行绝不能由执行者凭印象填。熔断/兜底之后
    R3 可能 2 秒就返回、transcript 里连 `codex attempt 1/1` 都没有，读起来像
    一轮正常的快速 round。
    """
    try:
        first = out_file.read_text(errors="replace").splitlines()[0].strip()
    except (OSError, IndexError):
        return ""
    return first if first.upper().startswith("CHALLENGER:") else f"⚠️ 第一行不是 CHALLENGER: —— {first[:60]!r}"


def gh_reviews(repo: str, pr: int, user: str):
    if not shutil.which("gh"):
        return None, "gh 不在 PATH 上"
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}/pulls/{pr}/reviews", "--paginate"],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return None, f"gh api 失败: {exc}"
    # 调试输出（GH_DEBUG）会混进 stdout，只取第一个 JSON 数组
    start = out.find("[")
    if start == -1:
        return None, "gh api 没有返回 JSON"
    try:
        data = json.loads(out[start:])
    except json.JSONDecodeError as exc:
        return None, f"JSON 解析失败: {exc}"
    mine = [r for r in data if (r.get("user") or {}).get("login") == user]
    return mine, None


def db_row(repo_bare: str, pr: int):
    if not EVAL_DB.is_file():
        return None
    con = sqlite3.connect(f"file:{EVAL_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(
            "SELECT * FROM model_review_runs WHERE repo=? AND pr_number=?"
            " ORDER BY id DESC LIMIT 1", (repo_bare, pr),
        )
        return cur.fetchone()
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="OWNER/REPO")
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--since", help="本轮 review 的起点 (STARTED_AT)，用来识别上一轮遗留的文件")
    ap.add_argument("--tmp", default="/tmp", help="中间产物目录 (默认 /tmp)")
    args = ap.parse_args()

    repo_bare = args.repo.split("/")[-1]
    n = args.pr
    tmp = Path(args.tmp)
    since = _parse_since(args.since)
    user = os.environ.get("PR_DAEMON_REVIEW_USER", "clestons")

    claims_backed, claims_total = 0, 0

    print(f"🧾 产物自检 — {args.repo}#{n}")
    if args.since and since is None:
        print(f"  {MISMATCH} --since 解析失败 ({args.since!r})，本次不做「早于本轮起点」判定")
    print("  （每一行都读自磁盘/GitHub/SQLite，不是回忆）")
    print()

    # ── 输入 ────────────────────────────────────────────────────────────────
    print("── 喂进去的 diff")
    for a in (
        Artifact("原始 diff", tmp / f"pr-{n}.diff", since),
        Artifact("压缩后 diff", tmp / f"pr-{n}-compressed.diff", since),
    ):
        claims_total += 1
        claims_backed += a.exists
        print(a.line())
    print()

    # ── R1 ──────────────────────────────────────────────────────────────────
    print("── R1 DeepSeek（自评里写「跑了 R1a/R1b」的依据）")
    r1_ran = {}
    for tag, label in (("r1a", "R1a 全量"), ("r1b", "R1b 安全")):
        a = Artifact(label, tmp / f"pr-{n}-{tag}.md", since)
        r1_ran[tag] = a.exists
        claims_total += 1
        claims_backed += a.exists
        print(a.line(count_findings(a.path) if a.exists else ""))
    if not any(r1_ran.values()):
        print("     ↳ 自评里若写「R1 未跑」，必须点名是哪一种正式豁免"
              "（纯文档/台账 · 增量=修我自己上一轮的 findings）；其他理由都不算理由。")
    print()

    # ── R2 / R4（Opus 走 Agent，天生不落盘）─────────────────────────────────
    print("── R2 / R4 Opus")
    for tag, label in (("r2", "R2 独立评审"), ("r4", "R4 最终裁决")):
        a = Artifact(label, tmp / f"pr-{n}-{tag}.md", since)
        claims_total += 1
        claims_backed += a.exists
        print(a.line())
    print("     ↳ Opus 走 Agent 工具，**默认什么都不留**。这两行是 ⚠️ 时不代表没跑，"
          "而代表『没有任何东西能证明跑了』—— 把 R2/R4 的返回原样存成上面这两个文件，"
          "这一行才有证据价值。")
    print()

    # ── R3 ──────────────────────────────────────────────────────────────────
    print("── R3 Codex PK（挑战者身份必须原样读，不许凭印象填）")
    out_file = tmp / f"pk-{n}-out.md"
    a = Artifact("PK 结论", out_file, since)
    claims_total += 1
    claims_backed += a.exists
    print(a.line(read_challenger(out_file) if a.exists else ""))
    for suffix, what in ((".raw", "codex 原始输出"), (".ds", "DeepSeek 兜底输出")):
        p = Path(str(out_file) + suffix)
        if p.is_file():
            st = p.stat()
            hint = ""
            if suffix == ".raw" and st.st_size < 2000:
                hint = "  ⚠️ 产出接近 0 —— 像静默挂起，不像一轮真的挑战"
            print(f"     · {what}: {st.st_size}B  {_fmt_age(st.st_mtime)}{hint}")
    print()

    # ── 结论到底发出去了没有 ────────────────────────────────────────────────
    print(f"── 结论是否真的 post 出去了（权威来源 = GitHub，不是我说发了）")
    claims_total += 1
    reviews, err = gh_reviews(args.repo, n, user)
    if err:
        print(f"  {MISSING}  查不到：{err}")
    elif not reviews:
        print(f"  {MISSING}  {user} 在这个 PR 上没有任何 review")
    else:
        claims_backed += 1
        last = reviews[-1]
        fresh = ""
        if since:
            sub = last.get("submitted_at")
            if sub:
                ts = datetime.fromisoformat(sub.replace("Z", "+00:00")).timestamp()
                fresh = "" if ts >= since else f"  {MISMATCH} 提交于本轮起点之前 —— 这是**上一轮**那条"
        print(f"  {OK}  {user} 共 {len(reviews)} 条；最新 id={last.get('id')} "
              f"state={last.get('state')} at={last.get('submitted_at')}{fresh}")
    print()

    # ── 台账里到底记了几轮 ──────────────────────────────────────────────────
    print("── SQLite 里记的轮数/模型（自评里那句 [N-round] 的出处）")
    claims_total += 1
    row = db_row(repo_bare, n)
    if row is None:
        print(f"  {MISSING}  model_review_runs 里没有 {repo_bare}#{n} 的行"
              f"（record-run 还没跑？）")
    else:
        claims_backed += 1
        print(f"  {OK}  id={row['id']}  verdict={row['verdict']}  "
              f"review_rounds={row['review_rounds']}  score={row['score']}")
        print(f"     · round_models: {row['round_models'] or MISSING}")
        print(f"     · round_timings: {row['round_timings'] or MISSING}")
        print(f"     · started_at={row['started_at'] or '—'}  finished_at={row['finished_at'] or '—'}"
              f"  duration={row['duration_seconds'] or '—'}s")

        # 交叉核对：台账声称的，和产物证明的，对不对得上
        claimed = (row["round_models"] or "").lower()
        print()
        print("── 交叉核对：台账声称 vs 产物证明")
        # ⚠️ 交叉核对必须只认**本轮**的产物。/tmp 里上一轮留下的 pk-N-out.md 会让
        # 「台账说跑了 Codex」和「磁盘上有 Codex 产物」对上，而这一轮根本没跑 ——
        # 正是这个脚本要消灭的那种「看起来一致」。
        def fresh(p: Path) -> bool:
            if not p.is_file():
                return False
            return not (since and p.stat().st_mtime < since)

        checks = [
            ("R1a", "r1a" in claimed or "deepseek" in claimed, fresh(tmp / f"pr-{n}-r1a.md")),
            ("R1b", "r1b" in claimed, fresh(tmp / f"pr-{n}-r1b.md")),
            ("R3 codex", "codex" in claimed, fresh(out_file)),
        ]
        if since is None:
            print("  ⚠️  未传 --since：无法区分本轮产物与上一轮残留，下面的核对只证明「文件存在」")
        for name, said, proved in checks:
            if said and not proved:
                print(f"  {MISMATCH}  round_models 说跑了 {name}，磁盘上没有它的产物")
            elif proved and not said:
                print(f"  ℹ️   有 {name} 的产物，但 round_models 没提它")
            else:
                print(f"  {OK}  {name}: 声称与产物一致")

    print()
    print(f"── 小结：{claims_backed}/{claims_total} 个事实字段有产物撑着。"
          f"{'  ⚠️ 剩下的请在自评块里如实写成「无产物」，不要用回忆补上。' if claims_backed < claims_total else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
