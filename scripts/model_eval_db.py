#!/usr/bin/env python3
"""Record and retrieve local-model review evaluations in SQLite."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
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
    with connect(args.db) as conn:
        cursor = conn.execute(
            """
            INSERT INTO model_review_runs (
                owner, repo, pr_number, pr_url, head_oid, provider, model,
                provider_base_url, thinking_mode, reasoning_effort, fallback_switched, local_review_path,
                score, verdict, summary, useful_findings, false_positives, misses,
                prompt_gaps, prior_improvements_applied, prior_improvement_evaluation,
                next_prompt_improvements, codex_adjudication, verification
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                args.prompt_gaps,
                args.prior_improvements_applied,
                args.prior_improvement_evaluation,
                "\n".join(next_items),
                args.codex_adjudication,
                args.verification,
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


def cmd_scorecard(args: argparse.Namespace) -> int:
    path = Path(args.db)
    if not path.exists():
        return 0
    with connect(args.db) as conn:
        runs = conn.execute(
            """
            SELECT id, created_at, head_oid, provider, model, local_review_path, fallback_switched, score, verdict, prior_improvement_evaluation
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
    provider_counts: dict[str, int] = {}
    provider_scores: dict[str, list[float]] = {}
    fallback_true = 0
    fallback_false = 0
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
    if provider_counts:
        print("provider_summary:")
        for provider, count in sorted(provider_counts.items(), key=lambda item: (-item[1], item[0])):
            provider_avg = sum(provider_scores[provider]) / len(provider_scores[provider])
            print(f"- {provider}: runs={count} avg_score={provider_avg:.2f}")
    if fallback_true or fallback_false:
        print(f"fallback_switched_true: {fallback_true}")
        print(f"fallback_switched_false: {fallback_false}")
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
        print(
            f"- #{row['id']} {row['created_at']} head={head} provider={provider}{fallback_text} "
            f"score={row['score']} verdict={row['verdict'] or ''}"
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
                   fallback_switched, score, verdict
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
                "verdicts": {},
            },
        )
        bucket["runs"] = int(bucket["runs"]) + 1
        cast_scores = bucket["scores"]
        assert isinstance(cast_scores, list)
        cast_scores.append(float(row["score"]))
        if row["fallback_switched"] == 1:
            bucket["fallback_true"] = int(bucket["fallback_true"]) + 1
        elif row["fallback_switched"] == 0:
            bucket["fallback_false"] = int(bucket["fallback_false"]) + 1
        verdict = str(row["verdict"] or "")
        cast_verdicts = bucket["verdicts"]
        assert isinstance(cast_verdicts, dict)
        cast_verdicts[verdict] = int(cast_verdicts.get(verdict, 0)) + 1

    scope = f" owner={args.owner}" if args.owner else ""
    if args.repo:
        scope += f" repo={args.repo}"
    print(f"Provider summary{scope} recent_runs={len(runs)}")
    for provider, bucket in sorted(buckets.items(), key=lambda item: (-int(item[1]['runs']), item[0])):
        scores = bucket["scores"]
        verdicts = bucket["verdicts"]
        assert isinstance(scores, list)
        assert isinstance(verdicts, dict)
        verdict_summary = ", ".join(f"{key or 'n/a'}={value}" for key, value in sorted(verdicts.items()))
        print(
            f"- {provider}: runs={bucket['runs']} avg_score={sum(scores) / len(scores):.2f} "
            f"min_score={min(scores):.2f} max_score={max(scores):.2f} "
            f"fallback_true={bucket['fallback_true']} fallback_false={bucket['fallback_false']} "
            f"verdicts=[{verdict_summary}]"
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
