#!/usr/bin/env python3
"""Run-count-driven patrol ladder with auto-stop.

Jason 2026-08-19: 触发词(开始 / loop / review)启动的巡检要**自己收敛**——
先立刻跑一次,然后 10 分钟一档跑 3 次,拉长到 20 分钟跑 3 次,30 分钟跑 3 次,
以此类推(+10),最后在 60 分钟档跑 1 次,**自动停**。

⚠️ 为什么不用 recurring cron:
  `4-59/N` 那套要求 N 整除 60,所以 40 / 50 做不出均匀间隔(实测 `*/40` 会变成
  40,40,20 的循环)。这里改用**一次性 cron**(`recurring:false`,把 分/时/日/月
  全钉死),每次跑完再排下一枚 —— 间隔任意、而且「不再排下一枚」天然就是停止,
  不需要 CronDelete,也就不存在「删了忘了建」把巡检悄悄弄没的风险。

⚠️ 这个脚本只管**节奏**,不碰任何审查逻辑。

状态文件: $PR_DAEMON_STATE_DIR/loop-ladder.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

# 每档的间隔(分钟),以及**空转几次**才升到下一档。最后一档空转满就停。
# ⚠️ 第二列数的是「空转」次数,不是「运行」次数 —— 见 cmd_next 里的 🔴。
LADDER: list[tuple[int, int]] = [
    (10, 3),
    (20, 3),
    (30, 3),
    (40, 3),
    (50, 3),
    (60, 1),
]

RUNGS = [m for m, _ in LADDER]
QUIET_TO_ADVANCE = [q for _, q in LADDER]

STATE_DIR = os.environ.get(
    "PR_DAEMON_STATE_DIR", "/Users/jason/Dev/tools/PR-Daemon/.state/pr-daemon"
)
STATE_PATH = os.path.join(STATE_DIR, "loop-ladder.json")


def _load() -> dict | None:
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _save(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)   # 原子替换:半写的状态文件会让梯子错档


def _runs() -> list[int]:
    """摊平成「第 i 次运行属于哪一档」(i 从 1 数)。"""
    out: list[int] = []
    for minutes, times in LADDER:
        out.extend([minutes] * times)
    return out


def _plan() -> list[int]:
    """「第 i 次跑完之后该等多少分钟」。

    🔴 **立刻那一次算 10 分钟档的第 1 次**(Jason 原话:「先运行一次,然后10分钟
       再一次,然后三次后开始延长为20分钟」)。所以第 r 次跑完之后要等的,是
       **第 r+1 次所属档位**的间隔 —— 而不是第 r 次自己的。

       第一版写成「等第 r 次自己的档位」,结果 10 分钟档跑了 4 次(t=0,10,20,30)
       才升档,每一档都多跑一次。自测把 16 次逐行打出来才看见,光读代码看不出。
    """
    runs = _runs()
    return [runs[i] for i in range(1, len(runs))]   # 最后一次跑完不再等 → 停


def _cron_for(when: datetime) -> str:
    """一次性 cron 表达式:分 时 日 月 *(星期不限)。"""
    return f"{when.minute} {when.hour} {when.day} {when.month} *"


def cmd_start(args: argparse.Namespace) -> int:
    state = {
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "runs_done": 0,
        "rung_idx": 0,
        "quiet_at_rung": 0,
        "consecutive_hits": 0,
        "trigger": args.trigger or "(未记录)",
    }
    _save(state)
    plan = _plan()
    print(json.dumps({
        "action": "run_now",
        "runs_total": len(_runs()),             # 含立刻那次
        "ladder": [{"every_min": m, "times": t} for m, t in LADDER],
        "total_span_min_if_all_quiet": sum(plan),
        "note": "先立刻跑一次;之后每轮按「有没有审到 PR」定档 —— 空转就爬,有活就贴。跨度只在【一路空转】时成立",
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    """记一次「已跑完」,给出下一枚一次性 cron;梯子走完则 STOP。

    🔴 **有活干就不许升档**(Jason 2026-08-19 追加):
       · `--reviewed N`(N>0)= 这一轮真审了 PR。
         - 连击第 1 次 → **保持当前档**,升档计数清零,而且**永不 stop**
           (哪怕已经在 60 分钟档 —— 有活的时候停掉是最糟的时机)。
         - 连击第 2 次及以后 → **每次降一档**(−10 分钟),下限 10 分钟。
       · `--reviewed 0` = 空转。连击清零,该档空转数 +1;满了就升一档;
         爬过最后一档才 stop。

       「连击」按**连续**算 —— 中间空转一次就重新数。理由:这个梯子表达的是
       「现在该多贴近」,而不是「历史上一共忙过几次」。
    """
    state = _load()
    if state is None:
        print(json.dumps({
            "action": "error",
            "why": "没有 loop-ladder.json —— 先跑 `loop_ladder.py start`",
        }, ensure_ascii=False))
        return 2

    reviewed = max(0, int(args.reviewed))
    idx = int(state.get("rung_idx", 0))
    quiet = int(state.get("quiet_at_rung", 0))
    hits = int(state.get("consecutive_hits", 0))

    state["runs_done"] = int(state.get("runs_done", 0)) + 1
    state["last_run_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    state["last_reviewed"] = reviewed

    if reviewed > 0:
        hits += 1
        quiet = 0                                   # 有活 → 升档计数作废
        if hits >= 2:
            before = idx
            idx = max(0, idx - 1)                   # 连击第 2 次起,每次降一档
            why = (f"连续第 {hits} 轮有活(本轮 {reviewed} 个 PR)—— "
                   f"降档 {RUNGS[before]}→{RUNGS[idx]} 分钟"
                   + ("(已到 10 分钟下限)" if idx == 0 and before == 0 else ""))
        else:
            why = f"本轮审了 {reviewed} 个 PR —— 保持 {RUNGS[idx]} 分钟档,不升档、不停止"
    else:
        hits = 0
        quiet += 1
        if quiet >= QUIET_TO_ADVANCE[idx]:
            quiet = 0
            idx += 1
            if idx >= len(RUNGS):
                state.update(rung_idx=len(RUNGS) - 1, quiet_at_rung=0,
                             consecutive_hits=0,
                             stopped_at=state["last_run_at"])
                _save(state)
                print(json.dumps({
                    "action": "stop",
                    "runs_done": state["runs_done"],
                    "why": "最后一档(60 分钟)也空转满了 —— 不再排下一枚 cron",
                }, ensure_ascii=False, indent=2))
                return 0
            why = f"空转,{RUNGS[idx - 1]} 分钟档已满 —— 升到 {RUNGS[idx]} 分钟"
        else:
            why = (f"空转 —— 保持 {RUNGS[idx]} 分钟档"
                   f"({quiet}/{QUIET_TO_ADVANCE[idx]} 次后升档)")

    wait = RUNGS[idx]
    when = datetime.now().astimezone() + timedelta(minutes=wait)
    state.update(rung_idx=idx, quiet_at_rung=quiet, consecutive_hits=hits,
                 next_at=when.isoformat(timespec="seconds"), next_wait_min=wait)
    _save(state)

    print(json.dumps({
        "action": "schedule",
        "runs_done": state["runs_done"],
        "reviewed": reviewed,
        "rung_min": wait,
        "wait_min": wait,
        "consecutive_hits": hits,
        "quiet_at_rung": quiet,
        "cron": _cron_for(when),
        "recurring": False,
        "fires_at": when.strftime("%Y-%m-%d %H:%M"),
        "why": why,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    state = _load()
    if state is None:
        print(json.dumps({"active": False, "why": "没有 loop-ladder.json"},
                         ensure_ascii=False, indent=2))
        return 0
    state["active"] = "stopped_at" not in state
    state["rung_min"] = RUNGS[int(state.get("rung_idx", 0))]
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def cmd_stop(_args: argparse.Namespace) -> int:
    state = _load() or {}
    state["stopped_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    state["stopped_by"] = "manual"
    _save(state)
    print(json.dumps({"action": "stop", "why": "手动停止"}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start", help="重置梯子,立刻跑第一次")
    p.add_argument("--trigger", help="触发词,只用于记录")
    p.set_defaults(func=cmd_start)

    n = sub.add_parser("next", help="记一次已跑完,给出下一枚一次性 cron 或 STOP")
    n.add_argument("--reviewed", type=int, default=0,
                   help="这一轮真审了几个 PR(=巡检汇报里的 k)。>0 就不升档;连续 2 轮起降档")
    n.set_defaults(func=cmd_next)
    sub.add_parser("status", help="当前进度").set_defaults(func=cmd_status)
    sub.add_parser("stop", help="手动停止梯子").set_defaults(func=cmd_stop)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
