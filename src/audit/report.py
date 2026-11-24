"""Markdown and JSON reporting for the Mealie MCP audit."""

from __future__ import annotations

import datetime as dt
import json
import os
from collections import defaultdict
from typing import Any

from .harness import Run

STATUS_ORDER = ("FAIL", "WARN", "SKIP", "PASS")


def summarize(run: Run) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {status: 0 for status in STATUS_ORDER}
    )
    for result in run.results:
        summary[result.domain][result.status] += 1
    return dict(summary)


def _is_nested_spec(spec: Any) -> bool:
    if not isinstance(spec, dict):
        return False
    if spec.get("type") == "object" or "properties" in spec:
        return True
    if spec.get("type") == "array":
        return _is_nested_spec(spec.get("items") or {})
    for variant in spec.get("anyOf") or []:
        if _is_nested_spec(variant):
            return True
    return False


def nested_parameters(tools: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for tool in tools:
        name = str(tool.get("name") or "")
        props = (tool.get("inputSchema") or {}).get("properties") or {}
        names = [prop for prop, spec in props.items() if _is_nested_spec(spec)]
        if names:
            result[name] = sorted(names)
    return result


def unexercised_nested(run: Run,
                       nested: dict[str, list[str]]) -> list[str]:
    # Partial domain runs cannot exercise every tool; enforce this gate only
    # for the full suite.
    if run.domains is not None:
        return []
    missing: list[str] = []
    for tool, props in nested.items():
        if tool not in run.tools_called:
            continue
        for prop in props:
            hit = any(
                result.tool == tool
                and result.args.get(prop) not in (None, "", [], {})
                for result in run.results
            )
            if not hit:
                missing.append(f"{tool}.{prop}")
    return sorted(missing)


def coverage(run: Run, live_tools: set[str]) -> dict[str, Any]:
    nested = nested_parameters(run.client.tools())
    return {
        "live": len(live_tools),
        "declared": len(run.declared_tools),
        "called": len(run.tools_called),
        "missing_contracts": sorted(live_tools - run.declared_tools),
        "unknown_contract_tools": sorted(run.declared_tools - live_tools),
        "uncalled": sorted(run.declared_tools - run.tools_called),
        "nested_parameter_count": sum(len(v) for v in nested.values()),
        "unexercised_nested": unexercised_nested(run, nested),
    }


def failures(run: Run) -> list[dict[str, Any]]:
    return [
        {
            "domain": r.domain,
            "scenario": r.scenario,
            "label": r.label,
            "tool": r.tool,
            "detail": r.detail,
            "args": r.args,
        }
        for r in run.results
        if r.status == "FAIL"
    ]


def write_json(run: Run, live_tools: set[str], path: str,
               metadata: dict[str, Any] | None = None) -> None:
    metadata = metadata or {}
    payload = {
        "run_id": run.run_id,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo": "mealie-mcp",
        "url": run.client.url,
        "identity": metadata.get("identity", {}),
        "tenant": metadata.get("tenant", {}),
        "fingerprint": metadata.get("fingerprint", {}),
        "coverage": coverage(run, live_tools),
        "summary": summarize(run),
        "failures": failures(run),
        "warnings": run.warnings,
        "results": [
            {
                "domain": r.domain,
                "scenario": r.scenario,
                "label": r.label,
                "tool": r.tool,
                "status": r.status,
                "detail": r.detail,
                "elapsed": r.elapsed,
                "args": r.args,
            }
            for r in run.results
        ],
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def write_markdown(run: Run, live_tools: set[str], path: str,
                   metadata: dict[str, Any] | None = None,
                   selected_domains: list[str] | None = None) -> None:
    metadata = metadata or {}
    cov = coverage(run, live_tools)
    summary = summarize(run)
    total_pass = sum(row["PASS"] for row in summary.values())
    total_fail = sum(row["FAIL"] for row in summary.values())
    total_warn = sum(row["WARN"] for row in summary.values())
    total_skip = sum(row["SKIP"] for row in summary.values())

    lines: list[str] = []
    lines.append("# Mealie MCP Tool Audit")
    lines.append("")
    lines.append(f"- **Run:** `{run.run_id}`")
    lines.append(f"- **Date:** {dt.datetime.now(dt.timezone.utc).isoformat()}")
    lines.append(f"- **Endpoint:** `{run.client.url}`")
    identity = metadata.get("identity", {})
    if identity:
        lines.append(f"- **User:** `{identity.get('username', '(unknown)')}`")
        lines.append(f"- **Admin:** `{identity.get('admin', '(unknown)')}`")
        lines.append(f"- **Group:** `{identity.get('groupSlug', '(unknown)')}`")
    tenant = metadata.get("tenant", {})
    if tenant:
        lines.append(f"- **Audit tenant:** `{tenant.get('group_name', '')}`")
    fingerprint = metadata.get("fingerprint", {})
    for key, value in fingerprint.items():
        lines.append(f"- **{key}:** `{value}`")
    if selected_domains:
        lines.append(f"- **Domains:** {', '.join(selected_domains)}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Domain | PASS | FAIL | SKIP | WARN |")
    lines.append("|---|---:|---:|---:|---:|")
    for domain in sorted(summary):
        row = summary[domain]
        lines.append(
            f"| {domain} | {row['PASS']} | {row['FAIL']} | "
            f"{row['SKIP']} | {row['WARN']} |"
        )
    lines.append(
        f"| **Total** | **{total_pass}** | **{total_fail}** | "
        f"**{total_skip}** | **{total_warn}** |"
    )
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- Live tools: **{cov['live']}**")
    lines.append(f"- Declared by contracts: **{cov['declared']}**")
    lines.append(f"- Called in this run: **{cov['called']}**")
    lines.append(f"- Tools with no contract: **{len(cov['missing_contracts'])}**")
    lines.append(f"- Nested object parameters: **{cov['nested_parameter_count']}**")
    lines.append(f"- Nested parameters never exercised: **{len(cov['unexercised_nested'])}**")
    for label, key in (
        ("Missing contracts", "missing_contracts"),
        ("Unknown contract tools", "unknown_contract_tools"),
        ("Declared but not reached", "uncalled"),
        ("Nested parameters never exercised", "unexercised_nested"),
    ):
        if cov[key]:
            lines.append("")
            lines.append(f"{label}:")
            lines.append("")
            for name in cov[key]:
                lines.append(f"- `{name}`")
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    failed = failures(run)
    if not failed:
        lines.append("No failures.")
    else:
        for item in failed:
            lines.append(
                f"### {item['domain']} / {item['scenario']} / {item['label']}"
            )
            lines.append("")
            lines.append(f"- Tool: `{item['tool']}`")
            if item["args"]:
                lines.append(f"- Args: `{json.dumps(item['args'], ensure_ascii=False)[:500]}`")
            lines.append("")
            lines.append("```")
            lines.append(item["detail"][:6000])
            lines.append("```")
            lines.append("")

    if run.warnings:
        lines.append("## Environment Warnings")
        lines.append("")
        for warning in run.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    warnings = [r for r in run.results if r.status == "WARN"]
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for item in warnings:
            lines.append(
                f"- `{item.domain}` / `{item.scenario}` / `{item.label}`: "
                f"{item.detail[:500]}"
            )
        lines.append("")

    skips = [r for r in run.results if r.status == "SKIP"]
    if skips:
        lines.append("## Skips")
        lines.append("")
        for item in skips:
            lines.append(f"- `{item.domain}` / `{item.label}`: {item.detail}")
        lines.append("")

    lines.append("## All Checks")
    lines.append("")
    current = None
    for result in run.results:
        key = (result.domain, result.scenario)
        if key != current:
            current = key
            lines.append(f"### {result.domain} / {result.scenario}")
            lines.append("")
        tool = f" (`{result.tool}`)" if result.tool else ""
        lines.append(f"- {result.status} {result.label}{tool}")
    lines.append("")

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")
