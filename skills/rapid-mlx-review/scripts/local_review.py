#!/usr/bin/env python3
"""Run a local Rapid-MLX first-pass review over a git diff."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path


SYSTEM_PROMPT = """You are a strict code reviewer. Report only findings that can plausibly cause bugs, regressions, security problems, performance problems, or meaningful missing tests. For each finding include severity, file/function clue, evidence, and a concrete fix. Avoid style-only advice, praise, broad refactors, and unsupported guesses.

Output contract:
- Do not include chain-of-thought, thinking process, analysis transcript, or step-by-step reasoning.
- Return concise review findings only.
- If prior review findings or improvement items are provided, explicitly verify whether each was fixed.
- For security gate reviews with adversarial examples, include a compact truth table: example, matched/missed, reason.
- If there are no issues, say so."""

REQUIRED_SECTIONS = [
    "Confirmed blockers",
    "Non-blocking hardening",
    "Prior findings verification",
    "False positives / uncertainty",
    "Confidence",
]

HIDDEN_REASONING_MARKERS = [
    "thinking process",
    "chain-of-thought",
    "step-by-step reasoning",
    "analyze user input",
    "synthesize findings",
    "the user wants",
    "let's examine",
    "i will formulate",
    "draft:",
    "check against constraints",
]


def review_quality_warnings(content: str, min_chars: int) -> list[str]:
    warnings: list[str] = []
    stripped = content.strip()
    if len(stripped) < min_chars:
        warnings.append(f"output too short: {len(stripped)} chars < {min_chars}")

    lower = stripped.lower()
    missing = [section for section in REQUIRED_SECTIONS if section.lower() not in lower]
    if missing:
        warnings.append("missing required sections: " + ", ".join(missing))

    markers = [marker for marker in HIDDEN_REASONING_MARKERS if marker in lower]
    if markers:
        warnings.append("contains hidden-reasoning markers: " + ", ".join(markers))
    return warnings


def load_prior_eval_context(db_path: str, owner: str, repo_name: str, pr_number: str) -> str:
    if not db_path or not owner or not repo_name or not pr_number:
        return ""
    path = Path(db_path).expanduser()
    if not path.exists():
        return ""

    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT improvement_text, status, evaluation
            FROM model_improvement_items
            WHERE owner = ? AND repo = ? AND pr_number = ?
            ORDER BY id DESC
            LIMIT 12
            """,
            (owner, repo_name, int(pr_number)),
        ).fetchall()
        run_rows = conn.execute(
            """
            SELECT created_at, score, prior_improvement_evaluation, next_prompt_improvements
            FROM model_review_runs
            WHERE owner = ? AND repo = ? AND pr_number = ?
            ORDER BY id DESC
            LIMIT 3
            """,
            (owner, repo_name, int(pr_number)),
        ).fetchall()
    except sqlite3.Error as exc:
        return f"Prior model-eval SQL context unavailable: {exc}"
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass

    if not rows and not run_rows:
        return ""

    lines = ["Prior local-model evaluation context from SQLite:"]
    if run_rows:
        lines.append("Recent run evaluations:")
        for row in run_rows:
            lines.append(
                f"- {row['created_at']}: score={row['score']}; "
                f"prior_improvement_evaluation={row['prior_improvement_evaluation'] or 'n/a'}; "
                f"next_prompt_improvements={row['next_prompt_improvements'] or 'n/a'}"
            )
    if rows:
        lines.append("Improvement items to apply or re-check:")
        for row in rows:
            lines.append(
                f"- [{row['status']}] {row['improvement_text']} "
                f"(evaluation: {row['evaluation'] or 'not evaluated yet'})"
            )
    return "\n".join(lines)


def run_git(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def repo_root(path: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"not a git repository: {path}")
    return Path(result.stdout.strip()).resolve()


def get_diff(repo: Path, base: str, target: str, worktree: bool) -> str:
    try:
        merge_base = run_git(repo, ["merge-base", base, target]).strip()
        diff = run_git(repo, ["diff", "--find-renames", "--find-copies", merge_base, target])
    except RuntimeError:
        diff = run_git(repo, ["diff", "--find-renames", "--find-copies", f"{base}...{target}"])

    if worktree:
        cached = run_git(repo, ["diff", "--find-renames", "--find-copies", "--cached"])
        unstaged = run_git(repo, ["diff", "--find-renames", "--find-copies"])
        sections = [diff]
        if cached.strip():
            sections.append("\n\n# Staged worktree diff\n\n" + cached)
        if unstaged.strip():
            sections.append("\n\n# Unstaged worktree diff\n\n" + unstaged)
        diff = "".join(sections)
    return diff


def chunk_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if size + len(line) > max_chars and current:
            chunks.append("".join(current))
            current = []
            size = 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def post_chat(base_url: str, model: str, messages: list[dict[str, str]], max_tokens: int, temperature: float) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Rapid-MLX server is not reachable at {url}: {exc}") from exc

    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected chat response: {body}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Rapid-MLX first-pass review on a git diff.")
    parser.add_argument("--repo", default=".", help="Repository path")
    parser.add_argument("--diff-file", default="", help="Review this diff file instead of generating a git diff")
    parser.add_argument("--context-file", action="append", default=[], help="Additional review context, prior findings, or adversarial cases")
    parser.add_argument("--base", default="origin/main", help="Base ref for review")
    parser.add_argument("--target", default="HEAD", help="Target ref for review")
    parser.add_argument("--worktree", action="store_true", help="Include staged and unstaged worktree changes")
    parser.add_argument("--base-url", default=os.environ.get("RAPID_MLX_BASE_URL", "http://localhost:8000/v1"))
    parser.add_argument("--model", default=os.environ.get("RAPID_MLX_MODEL", "qwen3.6-a3b"))
    parser.add_argument("--max-chars", type=int, default=45000, help="Approximate max diff chars per chunk")
    parser.add_argument("--max-tokens", type=int, default=3072, help="Max output tokens per local call")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--output", default="", help="Markdown output path")
    parser.add_argument("--min-output-chars", type=int, default=500, help="Minimum useful local review size before retry/warning")
    parser.add_argument("--retry-incomplete", type=int, default=1, help="Retry count for incomplete or contract-violating local output")
    parser.add_argument("--eval-db", default=os.environ.get("PR_DAEMON_MODEL_EVAL_DB", ""), help="Optional SQLite model-eval DB to load prior prompt improvements")
    parser.add_argument("--owner", default="", help="GitHub owner for SQL prior-eval lookup")
    parser.add_argument("--repo-name", default="", help="GitHub repository name for SQL prior-eval lookup")
    parser.add_argument("--pr-number", default="", help="GitHub PR number for SQL prior-eval lookup")
    args = parser.parse_args()

    if args.diff_file:
        repo = Path(args.repo).resolve()
        diff = Path(args.diff_file).read_text(encoding="utf-8")
    else:
        repo = repo_root(Path(args.repo).resolve())
        diff = get_diff(repo, args.base, args.target, args.worktree)
    if not diff.strip():
        print("No diff to review.")
        return 0

    extra_context = []
    for context_file in args.context_file:
        content = Path(context_file).read_text(encoding="utf-8").strip()
        if content:
            extra_context.append(f"Context from {context_file}:\n{content}")
    prior_eval_context = load_prior_eval_context(args.eval_db, args.owner, args.repo_name, args.pr_number)
    if prior_eval_context:
        extra_context.append(prior_eval_context)
    context_block = "\n\n".join(extra_context)

    chunks = chunk_text(diff, args.max_chars)
    reviews: list[str] = []
    quality_notes: list[str] = []
    started = time.strftime("%Y-%m-%d %H:%M:%S")

    for index, chunk in enumerate(chunks, start=1):
        user_prompt = textwrap.dedent(
            f"""
            Review git diff chunk {index}/{len(chunks)} from repository {repo.name}.
            Base: {args.base}
            Target: {args.target}
            {context_block}

            Required output sections:
            - Confirmed blockers
            - Non-blocking hardening
            - Prior findings verification
            - False positives / uncertainty
            - Confidence

            Diff:
            ```diff
            {chunk}
            ```
            """
        ).strip()
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
        content = post_chat(args.base_url, args.model, messages, args.max_tokens, args.temperature)

        warnings = review_quality_warnings(content, args.min_output_chars)
        for attempt in range(1, args.retry_incomplete + 1):
            if not warnings:
                break
            retry_prompt = textwrap.dedent(
                f"""
                Your previous review output was not usable for these reasons:
                - {'; '.join(warnings)}

                Re-run the review for the same diff. Return only these sections:
                - Confirmed blockers
                - Non-blocking hardening
                - Prior findings verification
                - False positives / uncertainty
                - Confidence

                Do not include hidden reasoning. Include concise evidence and concrete fixes only.

                Original review task:
                {user_prompt}
                """
            ).strip()
            content = post_chat(
                args.base_url,
                args.model,
                [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": retry_prompt}],
                args.max_tokens,
                args.temperature,
            )
            warnings = review_quality_warnings(content, args.min_output_chars)
            print(f"retried chunk {index}/{len(chunks)} for output quality attempt {attempt}", file=sys.stderr)
        if warnings:
            quality_notes.append(f"Chunk {index}: " + "; ".join(warnings))
        reviews.append(content.strip())
        print(f"reviewed chunk {index}/{len(chunks)}", file=sys.stderr)

    combined = "\n\n".join(f"## Chunk {i}\n\n{review}" for i, review in enumerate(reviews, start=1))
    quality_block = ""
    if quality_notes:
        quality_block = "Quality warnings:\n" + "\n".join(f"- {note}" for note in quality_notes) + "\n"
    output = textwrap.dedent(
        f"""
        # Rapid-MLX Local Review

        Started: {started}
        Repository: {repo}
        Base: {args.base}
        Target: {args.target}
        Model: {args.model}
        Base URL: {args.base_url}
        Chunks: {len(chunks)}
        {quality_block}

        {combined}
        """
    ).strip() + "\n"

    output_path = Path(args.output) if args.output else Path("/tmp") / f"rapid-mlx-local-review-{repo.name}.md"
    output_path.write_text(output, encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
