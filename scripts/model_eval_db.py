#!/usr/bin/env python3
"""Record and retrieve local-model review evaluations in SQLite."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


DEFAULT_DB = Path("reviews/model-evals/model-evals.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_review_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    pr_url TEXT,
    head_oid TEXT,
    provider TEXT,
    model TEXT,
    provider_base_url TEXT,
    thinking_mode TEXT,
    reasoning_effort TEXT,
    fallback_switched INTEGER,
    local_review_path TEXT,
    score REAL NOT NULL,
    verdict TEXT,
    summary TEXT,
    useful_findings TEXT,
    false_positives TEXT,
    misses TEXT,
    codex_override INTEGER,
    codex_only_findings INTEGER,
    prompt_gaps TEXT,
    prior_improvements_applied TEXT,
    prior_improvement_evaluation TEXT,
    next_prompt_improvements TEXT,
    codex_adjudication TEXT,
    verification TEXT
);

CREATE INDEX IF NOT EXISTS idx_model_review_runs_target
ON model_review_runs(owner, repo, pr_number, created_at);

CREATE TABLE IF NOT EXISTS model_improvement_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    source_run_id INTEGER NOT NULL,
    improvement_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    evaluation TEXT,
    carried_to_next INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(source_run_id) REFERENCES model_review_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_model_improvement_items_target
ON model_improvement_items(owner, repo, pr_number, status, id);

CREATE TABLE IF NOT EXISTS model_improvement_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    improvement_item_id INTEGER NOT NULL,
    assessed_run_id INTEGER,
    status TEXT NOT NULL,
    evaluation TEXT NOT NULL,
    FOREIGN KEY(improvement_item_id) REFERENCES model_improvement_items(id),
    FOREIGN KEY(assessed_run_id) REFERENCES model_review_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_model_improvement_assessments_item
ON model_improvement_assessments(improvement_item_id, created_at);
"""

ALLOWED_ITEM_STATUSES = {"proposed", "effective", "ineffective", "needs_followup", "retired"}
RUN_EXTRA_COLUMNS = {
    "provider": "TEXT",
    "provider_base_url": "TEXT",
    "thinking_mode": "TEXT",
    "reasoning_effort": "TEXT",
    "fallback_switched": "INTEGER",
    "codex_override": "INTEGER",
    "codex_only_findings": "INTEGER",
    # 每次 review 的耗时与轮次 —— 用来横向比较 pipeline 版本的成本/收益。
    "review_rounds": "INTEGER",      # 实际跑完的轮数(v4 = 2 或 4)
    "duration_seconds": "INTEGER",   # 从开审到 post 完成的墙钟秒数
    "started_at": "TEXT",            # ISO8601,开审时刻
    "finished_at": "TEXT",           # ISO8601,post 完成时刻
    # token 成本 —— 和 duration/rounds 一起，才能算「每条有效 finding 多少钱」。
    "input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
    "cost_usd": "REAL",
    # 每轮各自用了谁。既有的 provider/model 列只记 R1(DeepSeek)，pipeline 是 4 个模型，
    # 光看 provider 无法回答「这次 Opus 跑没跑 / Codex 是不是被 DeepSeek 兜底顶掉了」。
    "round_models": "TEXT",          # 例:R1=deepseek-v4-flash; R2/R4=opus; R3=codex
    # 分轮耗时/token。整次的 duration_seconds 回答不了「这 20 分钟里谁占的」,而那正是决定
    # 「要不要砍某一轮 / 值不值得流水线化」的唯一依据。存 JSON 而不是拆成多列:一次 review 是
    # 一个有 verdict/score 的完整单位,拆成多行后每行都得复制或留空 verdict,反而难查。
    "round_timings": "TEXT",         # JSON:{"r1a":47,"r1b":52,"verify":238,"r2":255,"r3":312,"r4":141,"post":8}
    "round_tokens": "TEXT",          # JSON:{"r1a":{"in":16000,"out":900},"r2":{...}} —— 缺的轮直接不写键
}


def connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(model_review_runs)").fetchall()
    }
    for column_name, column_type in RUN_EXTRA_COLUMNS.items():
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE model_review_runs ADD COLUMN {column_name} {column_type}")
    return conn


def validated_round_json(raw: str, flag: str) -> str | None:
    """空串 → 空串(该轮没测,存 NULL 语义)。合法 JSON 对象 → 原样。其它 → 报错返回 None。

    返回 None 表示「拒收」,调用方据此退出非零 —— 坏 JSON 静默入库后,任何按轮聚合的查询都会
    悄悄漏掉这一行,那比当场失败难查得多。
    """
    text = raw.strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"{flag} 不是合法 JSON: {exc}", file=sys.stderr)
        return None
    if not isinstance(parsed, dict):
        print(f"{flag} 必须是 JSON 对象(形如 {{\"r2\": 255}}),收到 {type(parsed).__name__}", file=sys.stderr)
        return None
    return text


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float | None:
    """按 token_cost.py 的 DeepSeek 价目表估成本(价格只有那一份,不在这里重打)。

    token_cost.py 拿不到(改名/搬走)就返回 None —— 记录流程不该因为估价失败而中断,
    NULL 也比一个凭空写死的价格强。
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import token_cost                                   # noqa: PLC0415 - 延迟导入,失败可降级
        return float(token_cost.estimate_cost(input_tokens, output_tokens)["total_cost"])
    except Exception:
        return None


def compute_duration_seconds(started_at: str, finished_at: str) -> int | None:
    """由 ISO8601 起止时刻算墙钟秒数;任一格式非法或倒序则返回 None(宁可不记也不记错)。"""
    def parse(value: str) -> datetime | None:
        text = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    start, end = parse(started_at), parse(finished_at)
    if start is None or end is None:
        return None
    # 一头带时区一头不带会直接抛 TypeError —— 统一按 naive 比,避免记录流程被打断。
    if (start.tzinfo is None) != (end.tzinfo is None):
        start, end = start.replace(tzinfo=None), end.replace(tzinfo=None)
    delta = int((end - start).total_seconds())
    return delta if delta >= 0 else None


def parse_boolish(value: str) -> int | None:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return 1
    if normalized in {"false", "0", "no"}:
        return 0
    return None


def load_local_review_metadata(local_review_path: str) -> dict[str, object]:
    if not local_review_path:
        return {}
    path = Path(local_review_path).expanduser()
    if not path.is_file():
        return {}

    metadata: dict[str, object] = {}
    key_map = {
        "Provider": "provider",
        "Model": "model",
        "Base URL": "provider_base_url",
        "Thinking Mode": "thinking_mode",
        "Reasoning Effort": "reasoning_effort",
        "Fallback Switched": "fallback_switched",
        "Conclusion": "local_verdict",
    }
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        label = label.strip()
        if label not in key_map:
            continue
        parsed_value: object = value.strip()
        if label == "Fallback Switched":
            parsed_bool = parse_boolish(str(parsed_value))
            parsed_value = parsed_bool if parsed_bool is not None else parsed_value
        elif label == "Conclusion":
            parsed_value = normalized_verdict_label(str(parsed_value))
        metadata[key_map[label]] = parsed_value
    return metadata


def normalized_provider_label(provider: str, model: str, local_review_path: str) -> str:
    provider = (provider or "").strip()
    model = (model or "").strip()
    if not provider and local_review_path:
        provider = str(load_local_review_metadata(local_review_path).get("provider", "")).strip()
    candidate = provider or model or "unknown"
    lowered = candidate.lower()
    if "deepseek" in lowered:
        return "deepseek"
    if "rapid-mlx" in lowered or "qwen3.6-a3b" in lowered:
        return "rapid-mlx"
    return candidate


def normalized_verdict_label(verdict: str) -> str:
    lowered = (verdict or "").strip().lower()
    if not lowered:
        return "unknown"
    if "request_changes" in lowered or "request changes" in lowered or "changes_requested" in lowered:
        return "request_changes"
    if "approve" in lowered or "approved" in lowered:
        return "approve"
    if "comment" in lowered or "commented" in lowered:
        return "comment"
    return lowered


def infer_codex_only_findings(misses: str) -> int:
    normalized = (misses or "").strip().lower()
    if not normalized or normalized in {"none", "- none.", "[]", "none.", "- none"}:
        return 0
    return 1


def infer_codex_override(local_verdict: str, final_verdict: str) -> int:
    normalized_local = normalized_verdict_label(local_verdict)
    normalized_final = normalized_verdict_label(final_verdict)
    if normalized_local == "unknown" or normalized_final == "unknown":
        return 0
    return 1 if normalized_local != normalized_final else 0


def parse_list(value: str) -> list[str]:
    if not value:
        return []
    value = value.strip()
    if not value:
        return []
    if value.startswith("["):
        parsed = json.loads(value)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("expected a JSON array of strings")
        return parsed
    return [line.strip() for line in value.splitlines() if line.strip()]


def parse_assessment(value: str) -> tuple[int, str, str]:
    parts = value.split(":", 2)
    if len(parts) != 3:
        raise ValueError("assessment must be ITEM_ID:STATUS:EVALUATION")
    item_id = int(parts[0])
    status = parts[1].strip()
    evaluation = parts[2].strip()
    if status not in ALLOWED_ITEM_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_ITEM_STATUSES))
        raise ValueError(f"status must be one of: {allowed}")
    if not evaluation:
        raise ValueError("assessment evaluation cannot be empty")
    return item_id, status, evaluation


def record_assessment(
    conn: sqlite3.Connection,
    item_id: int,
    status: str,
    evaluation: str,
    assessed_run_id: int | None,
) -> None:
    carried_to_next = 0 if status in {"effective", "retired"} else 1
    cursor = conn.execute(
        """
        UPDATE model_improvement_items
        SET status = ?, evaluation = ?, carried_to_next = ?
        WHERE id = ?
        """,
        (status, evaluation, carried_to_next, item_id),
    )
    if cursor.rowcount != 1:
        raise ValueError(f"unknown improvement item id: {item_id}")
    conn.execute(
        """
        INSERT INTO model_improvement_assessments (
            improvement_item_id, assessed_run_id, status, evaluation
        )
        VALUES (?, ?, ?, ?)
        """,
        (item_id, assessed_run_id, status, evaluation),
    )


def cmd_init(args: argparse.Namespace) -> int:
    with connect(args.db):
        pass
    print(args.db)
    return 0


def cmd_record_run(args: argparse.Namespace) -> int:
    next_items = parse_list(args.next_prompt_improvements)
    assessments = [parse_assessment(value) for value in args.assess_item]
    local_review_metadata = load_local_review_metadata(args.local_review_path)
    provider = args.provider or str(local_review_metadata.get("provider", ""))
    model = args.model or str(local_review_metadata.get("model", ""))
    provider_base_url = args.provider_base_url or str(local_review_metadata.get("provider_base_url", ""))
    thinking_mode = args.thinking_mode or str(local_review_metadata.get("thinking_mode", ""))
    reasoning_effort = args.reasoning_effort or str(local_review_metadata.get("reasoning_effort", ""))
    fallback_switched = args.fallback_switched
    if fallback_switched is None:
        inferred_fallback = local_review_metadata.get("fallback_switched")
        fallback_switched = inferred_fallback if isinstance(inferred_fallback, int) else None
    local_verdict = str(local_review_metadata.get("local_verdict", ""))
    codex_override = args.codex_override
    if codex_override is None:
        codex_override = infer_codex_override(local_verdict, args.verdict)
    codex_only_findings = args.codex_only_findings
    if codex_only_findings is None:
        codex_only_findings = infer_codex_only_findings(args.misses)
    # 只给了起止时刻就自己算耗时(显式 --duration-seconds 优先)。
    duration_seconds = args.duration_seconds
    if duration_seconds is None and args.started_at and args.finished_at:
        duration_seconds = compute_duration_seconds(args.started_at, args.finished_at)
    # 给了 token 数没给钱 → 用 token_cost.py 的价目表估(单一真源,别在这儿重打一份价格)。
    cost_usd = args.cost_usd
    if cost_usd is None and args.input_tokens is not None and args.output_tokens is not None:
        cost_usd = estimate_cost_usd(args.input_tokens, args.output_tokens)
    # 分轮数据必须是合法 JSON 对象,否则拒收 —— 存进一串坏字符串,下游查询会静默漏掉这一行,
    # 比明确报错难查得多。
    round_timings = validated_round_json(args.round_timings, "--round-timings")
    round_tokens = validated_round_json(args.round_tokens, "--round-tokens")
    if round_timings is None or round_tokens is None:
        return 2
    with connect(args.db) as conn:
        cursor = conn.execute(
            """
            INSERT INTO model_review_runs (
                owner, repo, pr_number, pr_url, head_oid, provider, model,
                provider_base_url, thinking_mode, reasoning_effort, fallback_switched, local_review_path,
                score, verdict, summary, useful_findings, false_positives, misses, codex_override, codex_only_findings,
                prompt_gaps, prior_improvements_applied, prior_improvement_evaluation,
                next_prompt_improvements, codex_adjudication, verification,
                review_rounds, duration_seconds, started_at, finished_at,
                input_tokens, output_tokens, cost_usd, round_models,
                round_timings, round_tokens
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                args.owner,
                args.repo,
                args.pr_number,
                args.pr_url,
                args.head_oid,
                provider,
                model,
                provider_base_url,
                thinking_mode,
                reasoning_effort,
                fallback_switched,
                args.local_review_path,
                args.score,
                args.verdict,
                args.summary,
                args.useful_findings,
                args.false_positives,
                args.misses,
                codex_override,
                codex_only_findings,
                args.prompt_gaps,
                args.prior_improvements_applied,
                args.prior_improvement_evaluation,
                "\n".join(next_items),
                args.codex_adjudication,
                args.verification,
                args.review_rounds,
                duration_seconds,
                args.started_at,
                args.finished_at,
                args.input_tokens,
                args.output_tokens,
                cost_usd,
                args.round_models,
                round_timings,
                round_tokens,
            ),
        )
        run_id = cursor.lastrowid
        for item in next_items:
            conn.execute(
                """
                INSERT INTO model_improvement_items (
                    owner, repo, pr_number, source_run_id, improvement_text, status, evaluation
                )
                VALUES (?, ?, ?, ?, ?, 'proposed', ?)
                """,
                (args.owner, args.repo, args.pr_number, run_id, item, "proposed for the next review"),
            )
        for item_id, status, evaluation in assessments:
            record_assessment(conn, item_id, status, evaluation, run_id)
    print(run_id)
    return 0


def cmd_assess_item(args: argparse.Namespace) -> int:
    with connect(args.db) as conn:
        record_assessment(conn, args.item_id, args.status, args.evaluation, args.assessed_run_id)
    print(args.item_id)
    return 0


def cmd_prior_context(args: argparse.Namespace) -> int:
    path = Path(args.db)
    if not path.exists():
        return 0
    with connect(args.db) as conn:
        runs = conn.execute(
            """
            SELECT created_at, score, prior_improvement_evaluation, next_prompt_improvements
            FROM model_review_runs
            WHERE owner = ? AND repo = ? AND pr_number = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (args.owner, args.repo, args.pr_number, args.limit),
        ).fetchall()
        items = conn.execute(
            """
            SELECT improvement_text, status, evaluation
            FROM model_improvement_items
            WHERE owner = ? AND repo = ? AND pr_number = ?
              AND carried_to_next = 1
            ORDER BY id DESC
            LIMIT ?
            """,
            (args.owner, args.repo, args.pr_number, args.limit * 4),
        ).fetchall()

    if not runs and not items:
        return 0

    print("Prior local-model SQL evaluation context:")
    for row in runs:
        print(f"- Run {row['created_at']}: score={row['score']}")
        if row["prior_improvement_evaluation"]:
            print(f"  prior improvement evaluation: {row['prior_improvement_evaluation']}")
        if row["next_prompt_improvements"]:
            print(f"  next improvements: {row['next_prompt_improvements']}")
    if items:
        print("Improvement items:")
        for row in items:
            print(f"- [{row['status']}] {row['improvement_text']} ({row['evaluation'] or 'not evaluated'})")
    return 0


def cmd_round_profile(args: argparse.Namespace) -> int:
    """「这 20 分钟到底谁占的」—— 跨 run 聚合 round_timings,回答该不该砍某一轮 / 值不值得流水线化。"""
    where, params = [], []
    if args.owner:
        where.append("owner = ?"); params.append(args.owner)
    if args.repo:
        where.append("repo = ?"); params.append(args.repo)
    if args.rounds is not None:
        where.append("review_rounds = ?"); params.append(args.rounds)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with connect(args.db) as conn:
        rows = conn.execute(
            f"""
            SELECT round_timings, duration_seconds, review_rounds, verdict
            FROM model_review_runs
            {clause}
            {'AND' if where else 'WHERE'} round_timings IS NOT NULL AND round_timings != ''
            ORDER BY id DESC LIMIT ?
            """,
            (*params, args.limit),
        ).fetchall()

    if not rows:
        print("还没有任何一行记了 round_timings —— 先让 record-run 带上 --round-timings。")
        return 0

    totals: dict[str, list[float]] = {}
    wall: list[int] = []
    for row in rows:
        try:
            timings = json.loads(row["round_timings"])
        except json.JSONDecodeError:
            continue        # 理论上进不来(写入时已校验),但老数据/手改过的行不该炸掉报表
        for stage, seconds in timings.items():
            if isinstance(seconds, (int, float)):
                totals.setdefault(str(stage), []).append(float(seconds))
        if row["duration_seconds"] is not None:
            wall.append(int(row["duration_seconds"]))

    if not totals:
        print("round_timings 里没有可用的数值字段。")
        return 0

    measured_total = sum(sum(v) for v in totals.values())
    print(f"round profile — {len(rows)} runs" + (f" (rounds={args.rounds})" if args.rounds is not None else ""))
    if wall:
        print(f"平均墙钟: {sum(wall) / len(wall) / 60:.1f} min/run")
    print(f"{'阶段':<10} {'次数':>5} {'均值s':>8} {'占比':>7}")
    for stage, values in sorted(totals.items(), key=lambda kv: -sum(kv[1])):
        share = sum(values) / measured_total * 100
        print(f"{stage:<10} {len(values):>5} {sum(values) / len(values):>8.0f} {share:>6.1f}%")
    if wall:
        # 有测量的阶段之和 vs 墙钟之和:差值就是没被计时的部分(我自己的思考/工具调用等)
        unmeasured = sum(wall) - measured_total
        if unmeasured > 0:
            print(f"\n未计时部分: {unmeasured / len(rows) / 60:.1f} min/run "
                  f"({unmeasured / sum(wall) * 100:.0f}% 的墙钟没被任何阶段覆盖)")
    return 0


def cmd_scorecard(args: argparse.Namespace) -> int:
    path = Path(args.db)
    if not path.exists():
        return 0
    with connect(args.db) as conn:
        runs = conn.execute(
            """
            SELECT id, created_at, head_oid, provider, model, local_review_path, fallback_switched,
                   score, verdict, codex_override, codex_only_findings, prior_improvement_evaluation,
                   review_rounds, duration_seconds, cost_usd, round_models
            FROM model_review_runs
            WHERE owner = ? AND repo = ? AND pr_number = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (args.owner, args.repo, args.pr_number, args.limit),
        ).fetchall()
        status_counts = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM model_improvement_items
            WHERE owner = ? AND repo = ? AND pr_number = ?
            GROUP BY status
            ORDER BY status
            """,
            (args.owner, args.repo, args.pr_number),
        ).fetchall()
        open_items = conn.execute(
            """
            SELECT id, improvement_text, status, evaluation
            FROM model_improvement_items
            WHERE owner = ? AND repo = ? AND pr_number = ? AND carried_to_next = 1
            ORDER BY id DESC
            LIMIT ?
            """,
            (args.owner, args.repo, args.pr_number, args.limit * 3),
        ).fetchall()

    if not runs:
        print("No model review runs recorded.")
        return 0

    scores = [float(row["score"]) for row in runs]
    print(f"Model review scorecard for {args.owner}/{args.repo}#{args.pr_number}")
    print(f"recent_runs: {len(runs)}")
    print(f"recent_score_avg: {sum(scores) / len(scores):.2f}")
    print(f"recent_score_min: {min(scores):.2f}")
    print(f"recent_score_max: {max(scores):.2f}")
    # 耗时/轮次:只统计真填了的行,老数据是 NULL 不能当 0 拉低均值。
    durations = [int(row["duration_seconds"]) for row in runs if row["duration_seconds"] is not None]
    rounds = [int(row["review_rounds"]) for row in runs if row["review_rounds"] is not None]
    if durations:
        print(f"recent_duration_avg_min: {sum(durations) / len(durations) / 60:.1f}")
        print(f"recent_duration_range_min: {min(durations) / 60:.1f}–{max(durations) / 60:.1f}")
    if rounds:
        print(f"recent_rounds: {'/'.join(str(r) for r in rounds)} (avg {sum(rounds) / len(rounds):.1f})")
    costs = [float(row["cost_usd"]) for row in runs if row["cost_usd"] is not None]
    if costs:
        print(f"recent_cost_total_usd: {sum(costs):.4f}  (avg {sum(costs) / len(costs):.4f}/run)")
    round_models = [str(row["round_models"]) for row in runs if row["round_models"]]
    if round_models:
        print(f"latest_round_models: {round_models[0]}")
    provider_counts: dict[str, int] = {}
    provider_scores: dict[str, list[float]] = {}
    fallback_true = 0
    fallback_false = 0
    codex_override_count = 0
    codex_only_findings_count = 0
    for row in runs:
        provider = normalized_provider_label(
            str(row["provider"] or ""),
            str(row["model"] or ""),
            str(row["local_review_path"] or ""),
        )
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        provider_scores.setdefault(provider, []).append(float(row["score"]))
        if row["fallback_switched"] == 1:
            fallback_true += 1
        elif row["fallback_switched"] == 0:
            fallback_false += 1
        if row["codex_override"] == 1:
            codex_override_count += 1
        if row["codex_only_findings"] == 1:
            codex_only_findings_count += 1
    if provider_counts:
        print("provider_summary:")
        for provider, count in sorted(provider_counts.items(), key=lambda item: (-item[1], item[0])):
            provider_avg = sum(provider_scores[provider]) / len(provider_scores[provider])
            print(f"- {provider}: runs={count} avg_score={provider_avg:.2f}")
    if fallback_true or fallback_false:
        print(f"fallback_switched_true: {fallback_true}")
        print(f"fallback_switched_false: {fallback_false}")
    print(f"codex_override_count: {codex_override_count}")
    print(f"codex_only_findings_count: {codex_only_findings_count}")
    print("runs:")
    for row in runs:
        head = (row["head_oid"] or "")[:7]
        provider = normalized_provider_label(
            str(row["provider"] or ""),
            str(row["model"] or ""),
            str(row["local_review_path"] or ""),
        )
        fallback_text = ""
        if row["fallback_switched"] == 1:
            fallback_text = " fallback=yes"
        elif row["fallback_switched"] == 0:
            fallback_text = " fallback=no"
        override_text = " override=yes" if row["codex_override"] == 1 else ""
        codex_only_text = " codex_only=yes" if row["codex_only_findings"] == 1 else ""
        print(
            f"- #{row['id']} {row['created_at']} head={head} provider={provider}{fallback_text} "
            f"score={row['score']} verdict={row['verdict'] or ''}{override_text}{codex_only_text}"
        )
        if row["prior_improvement_evaluation"]:
            print(f"  prior_improvement_evaluation: {row['prior_improvement_evaluation']}")
    if status_counts:
        print("improvement_status_counts:")
        for row in status_counts:
            print(f"- {row['status']}: {row['count']}")
    if open_items:
        print("open_improvement_items:")
        for row in open_items:
            print(f"- #{row['id']} [{row['status']}] {row['improvement_text']} ({row['evaluation'] or 'not evaluated'})")
    return 0


def cmd_provider_summary(args: argparse.Namespace) -> int:
    path = Path(args.db)
    if not path.exists():
        print("No model review runs recorded.")
        return 0
    with connect(args.db) as conn:
        runs = conn.execute(
            """
            SELECT owner, repo, pr_number, created_at, provider, model, local_review_path,
                   fallback_switched, score, verdict, codex_override, codex_only_findings
            FROM model_review_runs
            WHERE (? = '' OR owner = ?)
              AND (? = '' OR repo = ?)
            ORDER BY id DESC
            LIMIT ?
            """,
            (args.owner, args.owner, args.repo, args.repo, args.limit),
        ).fetchall()

    if not runs:
        print("No model review runs recorded.")
        return 0

    buckets: dict[str, dict[str, object]] = {}
    for row in runs:
        provider = normalized_provider_label(
            str(row["provider"] or ""),
            str(row["model"] or ""),
            str(row["local_review_path"] or ""),
        )
        bucket = buckets.setdefault(
            provider,
            {
                "runs": 0,
                "scores": [],
                "fallback_true": 0,
                "fallback_false": 0,
                "approve": 0,
                "request_changes": 0,
                "comment": 0,
                "unknown": 0,
                "codex_override": 0,
                "codex_only_findings": 0,
                "prs": set(),
            },
        )
        bucket["runs"] = int(bucket["runs"]) + 1
        cast_scores = bucket["scores"]
        assert isinstance(cast_scores, list)
        cast_scores.append(float(row["score"]))
        cast_prs = bucket["prs"]
        assert isinstance(cast_prs, set)
        cast_prs.add(f"{row['owner']}/{row['repo']}#{row['pr_number']}")
        if row["fallback_switched"] == 1:
            bucket["fallback_true"] = int(bucket["fallback_true"]) + 1
        elif row["fallback_switched"] == 0:
            bucket["fallback_false"] = int(bucket["fallback_false"]) + 1
        if row["codex_override"] == 1:
            bucket["codex_override"] = int(bucket["codex_override"]) + 1
        if row["codex_only_findings"] == 1:
            bucket["codex_only_findings"] = int(bucket["codex_only_findings"]) + 1
        verdict = normalized_verdict_label(str(row["verdict"] or ""))
        bucket[verdict] = int(bucket.get(verdict, 0)) + 1

    scope = f" owner={args.owner}" if args.owner else ""
    if args.repo:
        scope += f" repo={args.repo}"
    print(f"Provider summary{scope} recent_runs={len(runs)}")
    for provider, bucket in sorted(buckets.items(), key=lambda item: (-int(item[1]['runs']), item[0])):
        scores = bucket["scores"]
        assert isinstance(scores, list)
        prs = bucket["prs"]
        assert isinstance(prs, set)
        print(
            f"- {provider}: runs={bucket['runs']} unique_prs={len(prs)} avg_score={sum(scores) / len(scores):.2f} "
            f"min_score={min(scores):.2f} max_score={max(scores):.2f} "
            f"fallback_true={bucket['fallback_true']} fallback_false={bucket['fallback_false']} "
            f"approve={bucket['approve']} request_changes={bucket['request_changes']} "
            f"comment={bucket['comment']} unknown={bucket['unknown']} "
            f"codex_override={bucket['codex_override']} codex_only_findings={bucket['codex_only_findings']}"
        )
    return 0


def add_db_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record PR-Daemon local-model evaluations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize the SQLite schema")
    add_db_argument(init_parser)
    init_parser.set_defaults(func=cmd_init)

    prior_parser = subparsers.add_parser("prior-context", help="Print prior improvements for prompt context")
    add_db_argument(prior_parser)
    prior_parser.add_argument("--owner", required=True)
    prior_parser.add_argument("--repo", required=True)
    prior_parser.add_argument("--pr-number", type=int, required=True)
    prior_parser.add_argument("--limit", type=int, default=3)
    prior_parser.set_defaults(func=cmd_prior_context)

    p_round = subparsers.add_parser("round-profile", help="Aggregate per-round timings across runs")
    add_db_argument(p_round)
    p_round.add_argument("--owner", default="")
    p_round.add_argument("--repo", default="")
    p_round.add_argument("--rounds", type=int, default=None, help="只看 2 轮或 4 轮的")
    p_round.add_argument("--limit", type=int, default=50)
    p_round.set_defaults(func=cmd_round_profile)

    scorecard_parser = subparsers.add_parser("scorecard", help="Summarize recent model-review quality and open improvement items")
    add_db_argument(scorecard_parser)
    scorecard_parser.add_argument("--owner", required=True)
    scorecard_parser.add_argument("--repo", required=True)
    scorecard_parser.add_argument("--pr-number", type=int, required=True)
    scorecard_parser.add_argument("--limit", type=int, default=5)
    scorecard_parser.set_defaults(func=cmd_scorecard)

    provider_summary_parser = subparsers.add_parser("provider-summary", help="Summarize recent review quality by first-pass provider")
    add_db_argument(provider_summary_parser)
    provider_summary_parser.add_argument("--owner", default="")
    provider_summary_parser.add_argument("--repo", default="")
    provider_summary_parser.add_argument("--limit", type=int, default=50)
    provider_summary_parser.set_defaults(func=cmd_provider_summary)

    assess_parser = subparsers.add_parser("assess-item", help="Mark whether a prompt improvement item worked")
    add_db_argument(assess_parser)
    assess_parser.add_argument("--item-id", type=int, required=True)
    assess_parser.add_argument("--status", choices=sorted(ALLOWED_ITEM_STATUSES), required=True)
    assess_parser.add_argument("--evaluation", required=True)
    assess_parser.add_argument("--assessed-run-id", type=int, default=None)
    assess_parser.set_defaults(func=cmd_assess_item)

    record_parser = subparsers.add_parser("record-run", help="Insert one local-model evaluation run")
    add_db_argument(record_parser)
    record_parser.add_argument("--owner", required=True)
    record_parser.add_argument("--repo", required=True)
    record_parser.add_argument("--pr-number", type=int, required=True)
    record_parser.add_argument("--pr-url", default="")
    record_parser.add_argument("--head-oid", default="")
    record_parser.add_argument("--provider", default="")
    record_parser.add_argument("--model", default="")
    record_parser.add_argument("--provider-base-url", default="")
    record_parser.add_argument("--thinking-mode", default="")
    record_parser.add_argument("--reasoning-effort", default="")
    record_parser.add_argument("--fallback-switched", type=int, choices=[0, 1], default=None)
    record_parser.add_argument("--codex-override", type=int, choices=[0, 1], default=None)
    record_parser.add_argument("--codex-only-findings", type=int, choices=[0, 1], default=None)
    record_parser.add_argument("--review-rounds", type=int, default=None, help="实际跑完的轮数(v4 pipeline = 2 或 4)")
    record_parser.add_argument("--duration-seconds", type=int, default=None, help="本次 review 墙钟耗时(秒)")
    record_parser.add_argument("--started-at", default="", help="开审时刻 ISO8601")
    record_parser.add_argument("--finished-at", default="", help="post 完成时刻 ISO8601")
    record_parser.add_argument("--input-tokens", type=int, default=None, help="本次 review 输入 token")
    record_parser.add_argument("--output-tokens", type=int, default=None, help="本次 review 输出 token")
    record_parser.add_argument("--cost-usd", type=float, default=None,
                               help="本次 review 成本(USD);不给就按 token_cost.py 的 DeepSeek 价目自动估算")
    record_parser.add_argument("--round-models", default="",
                               help="每轮实际用的模型,例:'R1=deepseek-v4-flash; R2/R4=opus; R3=codex'")
    record_parser.add_argument("--round-timings", default="",
                               help='分轮耗时(秒)JSON,例 \'{"r1a":47,"r2":255,"r3":312,"r4":141}\';没测到的轮就别写那个键')
    record_parser.add_argument("--round-tokens", default="",
                               help='分轮 token JSON,例 \'{"r2":{"in":97000,"out":4000}}\'')
    record_parser.add_argument("--local-review-path", default="")
    record_parser.add_argument("--score", type=float, required=True)
    record_parser.add_argument("--verdict", default="")
    record_parser.add_argument("--summary", default="")
    record_parser.add_argument("--useful-findings", default="")
    record_parser.add_argument("--false-positives", default="")
    record_parser.add_argument("--misses", default="")
    record_parser.add_argument("--prompt-gaps", default="")
    record_parser.add_argument("--prior-improvements-applied", default="")
    record_parser.add_argument("--prior-improvement-evaluation", default="")
    record_parser.add_argument("--next-prompt-improvements", default="")
    record_parser.add_argument(
        "--assess-item",
        action="append",
        default=[],
        help="Assess prior improvement as ITEM_ID:STATUS:EVALUATION; repeatable",
    )
    record_parser.add_argument("--codex-adjudication", default="")
    record_parser.add_argument("--verification", default="")
    record_parser.set_defaults(func=cmd_record_run)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (sqlite3.Error, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
