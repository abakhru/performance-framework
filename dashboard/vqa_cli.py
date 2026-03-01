"""
vqa_cli.py — Command-line interface for Visual QA agent runs.

Usage (via justfile):
    just vqa https://example.com                          # all 31 agents
    just vqa https://example.com agents=marcus,mia        # specific agents
    just vqa-list                                         # list past runs
    just vqa-show <run_id>                                # show specific run

Direct usage:
    uv run python -m dashboard.vqa_cli https://example.com --agents marcus,mia
    uv run python -m dashboard.vqa_cli --list
    uv run python -m dashboard.vqa_cli --show <run_id>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure dashboard/ is on the path when invoked as __main__
_DASHBOARD_DIR = Path(__file__).parent.resolve()
if str(_DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_DIR))

from visual_qa import (  # noqa: E402
    VQARun,
    get_run,
    list_runs,
    load_profiles,
    start_run,
)

# ── ANSI colours ──────────────────────────────────────────────────────────────

_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_DIM = "\033[2m"


def _colour(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{code}{text}{_RESET}"


def _priority_colour(p: int) -> str:
    if p >= 8:
        return _RED
    if p >= 5:
        return _YELLOW
    return _GREEN


# ── Formatters ────────────────────────────────────────────────────────────────


def _print_run_summary(run: VQARun) -> None:
    total_bugs = sum(len(r.bugs) for r in run.results)
    critical = sum(1 for r in run.results for b in r.bugs if b.bug_priority >= 8)
    errors = [r for r in run.results if r.error]

    print(_colour(f"\n{'═' * 70}", _DIM))
    print(f"{_colour('Run ID:', _BOLD)} {run.run_id}")
    print(f"{_colour('URL:   ', _BOLD)} {run.url}")
    print(f"{_colour('Status:', _BOLD)} {_status_label(run.status)}")
    print(f"{_colour('Agents:', _BOLD)} {len(run.agents)}")
    print(f"{_colour('Bugs:  ', _BOLD)} {total_bugs} total  {_colour(f'{critical} critical (≥8)', _RED)}")
    if errors:
        print(f"{_colour('Errors:', _BOLD)} {len(errors)} agent(s) failed")
    if run.completed_at:
        print(f"{_colour('Done:  ', _BOLD)} {run.completed_at}")
    print(_colour(f"{'═' * 70}\n", _DIM))


def _status_label(status: str) -> str:
    if status == "done":
        return _colour("done", _GREEN)
    if status == "error":
        return _colour("error", _RED)
    return _colour(status, _YELLOW)


def _print_agent_results(run: VQARun) -> None:
    if not run.results:
        print(_colour("  (no results yet)", _DIM))
        return

    sorted_results = sorted(run.results, key=lambda r: -sum(b.bug_priority for b in r.bugs))
    for result in sorted_results:
        agent_label = _colour(f"{result.agent_name} — {result.specialty}", _BOLD)
        bug_count = len(result.bugs)
        if result.error:
            print(f"\n  {agent_label}  {_colour(f'ERROR: {result.error}', _RED)}")
            continue
        if bug_count == 0:
            print(f"\n  {agent_label}  {_colour('✓ no issues', _GREEN)}")
            continue

        print(f"\n  {agent_label}  {_colour(str(bug_count) + ' bug(s)', _YELLOW)}")
        for bug in sorted(result.bugs, key=lambda b: -b.bug_priority):
            p_label = _colour(f"P{bug.bug_priority}", _priority_colour(bug.bug_priority))
            c_label = _colour(f"C{bug.bug_confidence}", _DIM)
            types = ", ".join(bug.bug_type)
            print(f"    {p_label} {c_label}  {bug.bug_title}")
            print(f"           {_colour(types, _DIM)}")
            print(f"           {_colour(bug.bug_reasoning_why_a_bug[:120], _DIM)}")
            if bug.suggested_fix:
                print(f"           {_colour('Fix: ' + bug.suggested_fix[:100], _CYAN)}")


def _print_summary_table(run: VQARun) -> None:
    if not run.results:
        return
    print(_colour("\nSummary Table:", _BOLD))
    print(f"  {'Agent':<18} {'Specialty':<30} {'Bugs':>5} {'Max P':>6} {'Avg C':>6}")
    print(f"  {'-'*18} {'-'*30} {'-'*5} {'-'*6} {'-'*6}")
    for r in sorted(run.results, key=lambda r: -len(r.bugs)):
        max_p = max((b.bug_priority for b in r.bugs), default=0)
        avg_c = (sum(b.bug_confidence for b in r.bugs) / len(r.bugs)) if r.bugs else 0
        err = " ERR" if r.error else ""
        print(f"  {r.agent_name:<18} {r.specialty:<30} {len(r.bugs):>5} {max_p:>6} {avg_c:>6.1f}{err}")
    total = sum(len(r.bugs) for r in run.results)
    critical = sum(1 for r in run.results for b in r.bugs if b.bug_priority >= 8)
    print(f"\n  Total bugs: {total}   Critical (P≥8): {critical}")


# ── Commands ──────────────────────────────────────────────────────────────────


def cmd_run(url: str, agents: list[str], headers: dict[str, str], poll: bool = True) -> None:
    print(f"Starting Visual QA run for {_colour(url, _CYAN)}")
    agent_label = ", ".join(agents) if agents and agents != ["all"] else "all 31 agents"
    print(f"Agents: {agent_label}\n")

    run_id = start_run(url, agents, extra_headers=headers or None)
    print(f"Run ID: {run_id}")

    if not poll:
        print(f"Run started in background. Check status with: just vqa-show {run_id}")
        return

    # Poll until done
    spinner = ["|", "/", "-", "\\"]
    i = 0
    while True:
        run = get_run(run_id)
        if run is None:
            print(_colour("Error: run disappeared", _RED))
            sys.exit(1)
        if run.status in ("done", "error"):
            break
        sys.stdout.write(f"\r  {spinner[i % 4]} Running... (agents: {len(run.agents)})")
        sys.stdout.flush()
        i += 1
        time.sleep(2)

    print("\r" + " " * 60 + "\r", end="")  # clear spinner line
    _print_run_summary(run)
    _print_agent_results(run)
    _print_summary_table(run)

    if run.status == "error":
        print(_colour(f"\nRun failed: {run.error}", _RED))
        sys.exit(1)


def cmd_list() -> None:
    runs = list_runs(limit=20)
    if not runs:
        print("No past Visual QA runs found.")
        return

    print(_colour(f"\n{'Recent Visual QA Runs':^70}", _BOLD))
    print(f"  {'Run ID':<38} {'Status':<10} {'Agents':>7} {'Bugs':>5}  URL")
    print(f"  {'-'*38} {'-'*10} {'-'*7} {'-'*5}  {'-'*30}")
    for run in runs:
        total = sum(len(r.bugs) for r in run.results)
        url_short = run.url[:40] + ("…" if len(run.url) > 40 else "")
        print(f"  {run.run_id:<38} {run.status:<10} {len(run.agents):>7} {total:>5}  {url_short}")


def cmd_show(run_id: str) -> None:
    run = get_run(run_id)
    if run is None:
        print(_colour(f"Run {run_id!r} not found.", _RED))
        sys.exit(1)
    _print_run_summary(run)
    _print_agent_results(run)
    _print_summary_table(run)


def cmd_agents() -> None:
    profiles = load_profiles()
    groups: dict[str, list[dict]] = {}
    for p in profiles.values():
        groups.setdefault(p["group"], []).append(p)
    for group, agents in sorted(groups.items()):
        print(f"\n{_colour(group.upper(), _BOLD)}")
        for a in agents:
            types = ", ".join(a["check_types"])
            print(f"  {a['id']:<12} {a['name']:<12} {a['specialty']:<30} [{types}]")


# ── Argument parsing ──────────────────────────────────────────────────────────


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="vqa_cli",
        description="Visual QA — 31 specialist AI tester agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m dashboard.vqa_cli https://example.com
  python -m dashboard.vqa_cli https://example.com --agents marcus,mia,sophia
  python -m dashboard.vqa_cli --list
  python -m dashboard.vqa_cli --show <run_id>
  python -m dashboard.vqa_cli --agents
""",
    )
    parser.add_argument("url", nargs="?", help="URL to analyse")
    parser.add_argument(
        "--agents",
        default="all",
        help="Comma-separated agent IDs to run (default: all). Use --agents to list.",
    )
    parser.add_argument("--header", action="append", metavar="Name:Value", help="Extra HTTP header(s)")
    parser.add_argument("--no-poll", action="store_true", help="Return immediately without polling")
    parser.add_argument("--list", action="store_true", help="List past runs")
    parser.add_argument("--show", metavar="RUN_ID", help="Show a specific run")
    parser.add_argument("--agents-list", action="store_true", help="List all available agents")
    parser.add_argument("--json", action="store_true", help="Output raw JSON (for --show)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv or sys.argv[1:])

    if args.agents_list:
        cmd_agents()
        return

    if args.list:
        cmd_list()
        return

    if args.show:
        if args.json:
            run = get_run(args.show)
            if run is None:
                print(f"Run {args.show!r} not found.", file=sys.stderr)
                sys.exit(1)
            from dataclasses import asdict

            print(json.dumps(asdict(run), indent=2))
        else:
            cmd_show(args.show)
        return

    if not args.url:
        print("Error: url is required (or use --list / --show / --agents-list)", file=sys.stderr)
        sys.exit(1)

    # Parse agents
    agent_ids: list[str] = []
    if args.agents and args.agents.strip().lower() != "all":
        agent_ids = [a.strip() for a in args.agents.split(",") if a.strip()]

    # Parse extra headers
    headers: dict[str, str] = {}
    for h in args.header or []:
        if ":" in h:
            k, _, v = h.partition(":")
            headers[k.strip()] = v.strip()

    cmd_run(args.url, agent_ids, headers, poll=not args.no_poll)


if __name__ == "__main__":
    main()
