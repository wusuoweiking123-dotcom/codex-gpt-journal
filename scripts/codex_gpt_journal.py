#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "codex_home": "~/.codex",
    "journal_dir": "journal",
    "inbox_dir": "inbox",
    "commit_message_prefix": "daily ai journal",
    "privacy_mode": "summary",
    "max_snippet_chars": 360,
    "include_transcript": False,
}


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{12,})"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
]


def load_config(project_dir: Path) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    for name in ("config.example.json", "config.local.json"):
        path = project_dir / name
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                config.update(json.load(f))
    config["codex_home"] = str(Path(config["codex_home"]).expanduser())
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a daily Codex/GPT journal and optionally commit/push it.")
    parser.add_argument("--date", help="Date to render, YYYY-MM-DD. Defaults to today in local time.")
    parser.add_argument("--all", action="store_true", help="Render all dates found in the Codex session index.")
    parser.add_argument("--commit", action="store_true", help="Commit journal changes if this directory is a Git repo.")
    parser.add_argument("--push", action="store_true", help="Push after committing. Requires a configured Git remote.")
    parser.add_argument("--include-transcript", action="store_true", help="Include fuller conversation snippets. Use with care.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be rendered without writing files.")
    return parser.parse_args()


def local_today() -> str:
    return dt.datetime.now().astimezone().date().isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda m: m.group(0).split("=", 1)[0].split(":", 1)[0] + ": [REDACTED]", redacted)
    return redacted


def clean_text(text: str, max_chars: int) -> str:
    text = redact(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def is_boilerplate_message(text: str) -> bool:
    stripped = text.lstrip()
    boilerplate_prefixes = (
        "<recommended_plugins>",
        "# AGENTS.md instructions",
        "<environment_context>",
        "<developer_context>",
        "Capabilities from the `GitHub` plugin:",
    )
    return any(stripped.startswith(prefix) for prefix in boilerplate_prefixes)


def interesting_path_candidates(arguments: str) -> list[str]:
    paths: list[str] = []
    for match in re.findall(r"/Users/[^\s'\"`,;|)]+", arguments):
        path = match.rstrip(".,")
        if any(token in path for token in ("*", "?", ".codex/sessions/", ".codex/plugins/cache/")):
            continue
        if len(path) > 220:
            continue
        paths.append(path)
    return paths


def iso_to_date(value: str) -> str | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().date().isoformat()
    except ValueError:
        return value[:10] if re.match(r"\d{4}-\d{2}-\d{2}", value) else None


def session_file_for(codex_home: Path, session_id: str, date_hint: str) -> Path | None:
    y, m, d = date_hint.split("-")
    day_dir = codex_home / "sessions" / y / m / d
    if not day_dir.exists():
        return None
    matches = sorted(day_dir.glob(f"*{session_id}*.jsonl"))
    return matches[-1] if matches else None


def extract_message_text(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    role = payload.get("role")
    content = payload.get("content")
    if not role or not content:
        return None, None
    parts: list[str] = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("input_text") or item.get("output_text")
                if value:
                    parts.append(str(value))
    elif isinstance(content, str):
        parts.append(content)
    text = "\n".join(parts).strip()
    return (role, text) if text else (None, None)


def summarize_session(path: Path, title: str, updated_at: str, max_chars: int, include_transcript: bool) -> dict[str, Any]:
    rows = read_jsonl(path)
    user_messages: list[str] = []
    assistant_messages: list[str] = []
    touched_files: set[str] = set()
    command_count = 0

    for row in rows:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        row_type = row.get("type")

        if row_type == "response_item" and payload.get("type") == "message":
            role, text = extract_message_text(payload)
            if text and is_boilerplate_message(text):
                continue
            if role == "user":
                user_messages.append(text or "")
            elif role == "assistant":
                assistant_messages.append(text or "")

        if row_type == "event_msg" and payload.get("type") == "user_message":
            message = payload.get("message")
            if message and not is_boilerplate_message(str(message)):
                user_messages.append(str(message))

        if row_type == "response_item" and payload.get("type") == "function_call":
            command_count += 1
            arguments = payload.get("arguments")
            if isinstance(arguments, str):
                for path in interesting_path_candidates(arguments):
                    touched_files.add(path)

    return {
        "title": title or path.stem,
        "updated_at": updated_at,
        "path": str(path),
        "user_count": len(user_messages),
        "assistant_count": len(assistant_messages),
        "command_count": command_count,
        "first_user": clean_text(user_messages[0], max_chars) if user_messages else "",
        "last_user": clean_text(user_messages[-1], max_chars) if user_messages else "",
        "last_assistant": clean_text(assistant_messages[-1], max_chars) if assistant_messages else "",
        "touched_files": sorted(touched_files)[:12],
        "transcript": [
            {"role": "user", "text": clean_text(text, max_chars * 2)}
            for text in user_messages[:20]
        ]
        + [
            {"role": "assistant", "text": clean_text(text, max_chars * 2)}
            for text in assistant_messages[:20]
        ]
        if include_transcript
        else [],
    }


def collect_codex_sessions(codex_home: Path, target_dates: set[str], max_chars: int, include_transcript: bool) -> dict[str, list[dict[str, Any]]]:
    index_path = codex_home / "session_index.jsonl"
    rows = read_jsonl(index_path)
    grouped: dict[str, list[dict[str, Any]]] = {date: [] for date in target_dates}

    for row in rows:
        session_id = str(row.get("id") or "")
        title = str(row.get("thread_name") or "")
        updated_at = str(row.get("updated_at") or "")
        day = iso_to_date(updated_at)
        if not session_id or not day or day not in target_dates:
            continue
        session_path = session_file_for(codex_home, session_id, day)
        if not session_path:
            continue
        grouped.setdefault(day, []).append(summarize_session(session_path, title, updated_at, max_chars, include_transcript))

    for sessions in grouped.values():
        sessions.sort(key=lambda x: x.get("updated_at", ""))
    return grouped


def all_dates_from_index(codex_home: Path) -> set[str]:
    dates: set[str] = set()
    for row in read_jsonl(codex_home / "session_index.jsonl"):
        day = iso_to_date(str(row.get("updated_at") or ""))
        if day:
            dates.add(day)
    return dates


def read_inbox(project_dir: Path, inbox_dir: str, day: str) -> str:
    path = project_dir / inbox_dir / f"{day}.md"
    if not path.exists():
        return ""
    return redact(path.read_text(encoding="utf-8", errors="replace")).strip()


def render_day(day: str, sessions: list[dict[str, Any]], inbox_text: str) -> str:
    lines: list[str] = []
    lines.append(f"# AI 工作日志：{day}")
    lines.append("")
    lines.append("> 自动整理自本机 Codex session 与手动 ChatGPT inbox。默认只放摘要，不放完整隐私对话。")
    lines.append("")
    lines.append("## 今日概览")
    lines.append("")
    lines.append(f"- Codex 会话数：{len(sessions)}")
    lines.append(f"- ChatGPT inbox：{'有' if inbox_text else '无'}")
    lines.append(f"- 生成时间：{dt.datetime.now().astimezone().isoformat(timespec='seconds')}")
    lines.append("")

    if sessions:
        lines.append("## Codex 交互")
        lines.append("")
        for idx, session in enumerate(sessions, start=1):
            lines.append(f"### {idx}. {session['title']}")
            lines.append("")
            lines.append(f"- 更新时间：{session['updated_at']}")
            lines.append(f"- 用户消息 / 助手消息：{session['user_count']} / {session['assistant_count']}")
            lines.append(f"- 工具调用数：{session['command_count']}")
            if session["first_user"]:
                lines.append(f"- 开始问题：{session['first_user']}")
            if session["last_user"] and session["last_user"] != session["first_user"]:
                lines.append(f"- 最近问题：{session['last_user']}")
            if session["last_assistant"]:
                lines.append(f"- 最近结果：{session['last_assistant']}")
            if session["touched_files"]:
                lines.append("- 相关文件：")
                for path in session["touched_files"]:
                    lines.append(f"  - `{path}`")
            if session["transcript"]:
                lines.append("")
                lines.append("<details>")
                lines.append("<summary>展开摘要转录</summary>")
                lines.append("")
                for item in session["transcript"]:
                    lines.append(f"**{item['role']}**: {item['text']}")
                    lines.append("")
                lines.append("</details>")
            lines.append("")
    else:
        lines.append("## Codex 交互")
        lines.append("")
        lines.append("- 今天还没有发现 Codex session。")
        lines.append("")

    lines.append("## ChatGPT / GPT 交互")
    lines.append("")
    if inbox_text:
        lines.append(inbox_text)
        lines.append("")
    else:
        lines.append(f"- 暂无手动记录。可以把当天 ChatGPT 摘要放到 `inbox/{day}.md`。")
        lines.append("")

    lines.append("## 下一步")
    lines.append("")
    lines.append("- [ ] 补充今天 GPT 网页端的关键讨论")
    lines.append("- [ ] 回看 Codex 产出，标记可复用的方法/代码")
    lines.append("- [ ] 如果有实际项目变更，把相关仓库也同步提交")
    lines.append("")

    return "\n".join(lines)


def write_journal(project_dir: Path, journal_dir: str, day: str, content: str, dry_run: bool) -> Path:
    month = day[:7]
    out_dir = project_dir / journal_dir / month
    out_path = out_dir / f"{day}.md"
    if dry_run:
        print(f"Would write {out_path}")
        print(content[:1200])
        return out_path
    out_dir.mkdir(parents=True, exist_ok=True)
    old = out_path.read_text(encoding="utf-8") if out_path.exists() else None
    if old != content:
        out_path.write_text(content, encoding="utf-8")
    return out_path


def run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def is_git_repo(project_dir: Path) -> bool:
    result = run_git(["rev-parse", "--is-inside-work-tree"], project_dir, check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def has_changes(project_dir: Path) -> bool:
    result = run_git(["status", "--porcelain"], project_dir, check=False)
    return bool(result.stdout.strip())


def commit_and_maybe_push(project_dir: Path, message: str, push: bool) -> None:
    if not is_git_repo(project_dir):
        print("Not a Git repository yet; journal files were generated but not committed.", file=sys.stderr)
        return
    if not has_changes(project_dir):
        print("No journal changes to commit.")
        return
    run_git(["add", "journal", "inbox", "README.md", "config.example.json", "scripts", ".gitignore"], project_dir)
    if not has_changes(project_dir):
        print("No staged journal changes to commit.")
        return
    run_git(["commit", "-m", message], project_dir)
    print(f"Committed: {message}")
    if push:
        result = run_git(["push"], project_dir, check=False)
        if result.returncode != 0:
            print(result.stderr.strip() or "git push failed; check remote configuration.", file=sys.stderr)
            raise SystemExit(result.returncode)
        print("Pushed to GitHub.")


def main() -> int:
    args = parse_args()
    project_dir = Path(__file__).resolve().parents[1]
    config = load_config(project_dir)
    codex_home = Path(config["codex_home"]).expanduser()
    include_transcript = bool(args.include_transcript or config.get("include_transcript"))
    max_chars = int(config.get("max_snippet_chars") or 360)

    if args.all:
        target_dates = all_dates_from_index(codex_home)
        if not target_dates:
            target_dates = {args.date or local_today()}
    else:
        target_dates = {args.date or local_today()}

    grouped = collect_codex_sessions(codex_home, target_dates, max_chars, include_transcript)
    written: list[Path] = []
    for day in sorted(target_dates):
        inbox_text = read_inbox(project_dir, config["inbox_dir"], day)
        content = render_day(day, grouped.get(day, []), inbox_text)
        written.append(write_journal(project_dir, config["journal_dir"], day, content, args.dry_run))

    if args.commit and not args.dry_run:
        if len(target_dates) == 1:
            day = next(iter(target_dates))
            message = f"{config['commit_message_prefix']}: {day}"
        else:
            message = f"{config['commit_message_prefix']}: refresh archive"
        commit_and_maybe_push(project_dir, message, args.push)

    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
