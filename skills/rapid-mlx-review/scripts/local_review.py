#!/usr/bin/env python3
"""Run a local Rapid-MLX first-pass review over a git diff."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path


SYSTEM_PROMPT = """You are a strict code reviewer. Report only findings that can plausibly cause bugs, regressions, security problems, performance problems, or meaningful missing tests. For each finding include severity, file/function clue, evidence, and a concrete fix. Avoid style-only advice, praise, broad refactors, and unsupported guesses. If there are no issues, say so."""


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
    parser.add_argument("--base", default="origin/main", help="Base ref for review")
    parser.add_argument("--target", default="HEAD", help="Target ref for review")
    parser.add_argument("--worktree", action="store_true", help="Include staged and unstaged worktree changes")
    parser.add_argument("--base-url", default=os.environ.get("RAPID_MLX_BASE_URL", "http://localhost:8000/v1"))
    parser.add_argument("--model", default=os.environ.get("RAPID_MLX_MODEL", "default"))
    parser.add_argument("--max-chars", type=int, default=45000, help="Approximate max diff chars per chunk")
    parser.add_argument("--max-tokens", type=int, default=3072, help="Max output tokens per local call")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--output", default="", help="Markdown output path")
    args = parser.parse_args()

    repo = repo_root(Path(args.repo).resolve())

    diff = get_diff(repo, args.base, args.target, args.worktree)
    if not diff.strip():
        print("No diff to review.")
        return 0

    chunks = chunk_text(diff, args.max_chars)
    reviews: list[str] = []
    started = time.strftime("%Y-%m-%d %H:%M:%S")

    for index, chunk in enumerate(chunks, start=1):
        user_prompt = textwrap.dedent(
            f"""
            Review git diff chunk {index}/{len(chunks)} from repository {repo.name}.
            Base: {args.base}
            Target: {args.target}

            Diff:
            ```diff
            {chunk}
            ```
            """
        ).strip()
        content = post_chat(
            args.base_url,
            args.model,
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
            args.max_tokens,
            args.temperature,
        )
        reviews.append(content.strip())
        print(f"reviewed chunk {index}/{len(chunks)}", file=sys.stderr)

    combined = "\n\n".join(f"## Chunk {i}\n\n{review}" for i, review in enumerate(reviews, start=1))
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
