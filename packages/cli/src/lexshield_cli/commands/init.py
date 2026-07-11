"""Scaffold lexshield.yaml, policy.yaml, and rules.yaml (SPEC §9.E init)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

import typer
from rich.console import Console

from lexshield_cli.commands.packs import _pack_dir

console = Console()

PackName = Literal["baseline-deny", "pii-guard", "change-window"]

LEXSHIELD_YAML = """\
version: 1
shield:
  id: local
  name: local-shield
  policy: ./policy.yaml
  classifiers:
    - type: deterministic
      path: ./rules.yaml
  fail_on_classifier_error: BLOCK
  sinks:
    - type: stdout
    - type: file
      path: ./traces.ndjson
server:
  host: 127.0.0.1
  port: 8787
  token_env: LEXSHIELD_LOCAL_TOKEN
"""

RULES_YAML = """\
version: 1
tool_map:
  health_check: network.request.health
  ping: network.request.health
  send_email: comms.send.email
  send_slack: comms.send.slack
  http_request: network.request.http
  execute_sql: data.query.sql
  delete_resource: infra.delete.resource
  create_resource: infra.provision.resource
  update_resource: infra.mutate.resource
  create_charge: finance.charge.create
  transfer_funds: finance.transfer.create
  run_shell: code.execute.shell
  write_file: code.write.repo
patterns:
  - name: aws_access_key
    match:
      any_arg_regex: "AKIA[0-9A-Z]{16}"
    intent: security.secret_exposure
    confidence: 0.98
  - name: openai_sk
    match:
      any_arg_regex: "sk-(proj-)?[a-zA-Z0-9]{20,}"
    intent: security.secret_exposure
    confidence: 0.98
"""

CHALLENGE_DELETE_RULE = """\
  - id: challenge-delete-prod
    name: Challenge destructive actions in production
    priority: 200
    match:
      environments: ["production"]
      intents: ["infra.delete.resource", "data.delete.record"]
    verdict: CHALLENGE
    reason: "Destructive action in production requires approval"
    challenge:
      channel: stdout
      timeoutSeconds: 3600
      onTimeout: BLOCK

"""

POLICY_TEMPLATES: dict[PackName, str] = {
    "baseline-deny": """\
version: 1
id: baseline-deny
name: Baseline default deny
description: Default deny with safe health and metrics allowlist.
defaultVerdict: BLOCK
rules:
  - id: allow-health
    name: Allow health checks
    priority: 100
    match:
      tools: ["health_check", "ping"]
      intents: ["network.request.health"]
    verdict: ALLOW
    reason: "Health checks are always allowed"

  - id: challenge-delete-prod
    name: Challenge destructive actions in production
    priority: 200
    match:
      environments: ["production"]
      intents: ["infra.delete.resource", "data.delete.record"]
    verdict: CHALLENGE
    reason: "Destructive action in production requires approval"
    challenge:
      channel: stdout
      timeoutSeconds: 3600
      onTimeout: BLOCK

  - id: block-secret-exposure
    name: Block secret exposure
    priority: 300
    match:
      intents: ["security.secret_exposure"]
    verdict: BLOCK
    reason: "Possible secret exposure in tool arguments"

  - id: block-exfil
    name: Block exfiltration
    priority: 300
    match:
      intents: ["data.exfiltrate"]
    verdict: BLOCK
    reason: "Possible data exfiltration"
""",
    "pii-guard": """\
version: 1
id: pii-guard
name: PII egress guard
description: Extends baseline; challenges external comms when tagged pii; blocks non-allowlisted HTTP.
defaultVerdict: BLOCK
rules:
  - id: allow-health
    priority: 100
    match:
      tools: ["health_check", "ping"]
      intents: ["network.request.health"]
    verdict: ALLOW
    reason: "Health checks are always allowed"

  - id: challenge-pii-email
    priority: 220
    match:
      intents: ["comms.send.email", "comms.send.external"]
      tags:
        data_class: ["pii"]
    verdict: CHALLENGE
    reason: "Sending PII requires approval"
    challenge:
      channel: stdout
      timeoutSeconds: 3600
      onTimeout: BLOCK

  - id: block-http-non-allowlist
    priority: 250
    match:
      intents: ["network.request.http"]
      expression: '!(args.url startsWith "https://api.mycompany.com/")'
    verdict: BLOCK
    reason: "HTTP to non-allowlisted host"

  - id: block-secret-exposure
    priority: 300
    match:
      intents: ["security.secret_exposure"]
    verdict: BLOCK
    reason: "Possible secret exposure in tool arguments"

  - id: block-exfil
    priority: 300
    match:
      intents: ["data.exfiltrate"]
    verdict: BLOCK
    reason: "Possible data exfiltration"
""",
    "change-window": """\
version: 1
id: change-window
name: Infra change window
description: Infra mutate/provision in production requires change_ticket tag; otherwise challenge.
defaultVerdict: BLOCK
rules:
  - id: allow-health
    priority: 100
    match:
      tools: ["health_check", "ping"]
      intents: ["network.request.health"]
    verdict: ALLOW
    reason: "Health checks are always allowed"

  - id: allow-infra-with-ticket
    priority: 180
    match:
      environments: ["production"]
      intents: ["infra.mutate.resource", "infra.provision.resource"]
      expression: 'tags.change_ticket != ""'
    verdict: ALLOW
    reason: "Change ticket present"

  - id: challenge-infra-prod
    priority: 200
    match:
      environments: ["production"]
      intents: ["infra.mutate.resource", "infra.provision.resource", "infra.delete.resource"]
    verdict: CHALLENGE
    reason: "Production infra change requires approval"
    challenge:
      channel: stdout
      timeoutSeconds: 3600
      onTimeout: BLOCK

  - id: block-secret-exposure
    priority: 300
    match:
      intents: ["security.secret_exposure"]
    verdict: BLOCK
    reason: "Possible secret exposure in tool arguments"
""",
}

GITIGNORE_ENTRIES = """\
# LexShield local artifacts
traces.ndjson
.lexshield/
"""


def _write_file(path: Path, content: str, *, force: bool) -> None:
    if path.exists() and not force:
        console.print(f"[yellow]skip[/yellow] {path} (already exists)")
        return
    path.write_text(content, encoding="utf-8")
    console.print(f"[green]wrote[/green] {path}")


def _ensure_baseline_challenge_delete(policy_content: str) -> str:
    """Embed challenge-delete-prod in baseline template when missing."""
    if "challenge-delete-prod" in policy_content:
        return policy_content
    marker = '  - id: block-secret-exposure'
    if marker not in policy_content:
        return policy_content
    return policy_content.replace(marker, CHALLENGE_DELETE_RULE + marker, 1)


def _write_rules_from_pack(cwd: Path, pack: PackName, *, force: bool) -> None:
    """Copy rules.yaml from built-in pack when available."""
    rules_dest = cwd / "rules.yaml"
    pack_dir = _pack_dir(pack)
    if pack_dir is not None:
        rules_src = pack_dir / "rules.yaml"
        if rules_src.is_file():
            if rules_dest.exists() and not force:
                console.print(f"[yellow]skip[/yellow] {rules_dest} (already exists)")
                return
            shutil.copy2(rules_src, rules_dest, follow_symlinks=True)
            console.print(f"[green]wrote[/green] {rules_dest} (from pack {pack})")
            return
    _write_file(rules_dest, RULES_YAML, force=force)


def _ensure_gitignore(cwd: Path) -> None:
    gitignore = cwd / ".gitignore"
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")
        if "traces.ndjson" in existing and ".lexshield/" in existing:
            return
        gitignore.write_text(existing.rstrip() + "\n\n" + GITIGNORE_ENTRIES, encoding="utf-8")
    else:
        gitignore.write_text(GITIGNORE_ENTRIES.strip() + "\n", encoding="utf-8")
    console.print(f"[green]updated[/green] {gitignore}")


def init(
    pack: PackName = typer.Option(
        "baseline-deny",
        "--pack",
        help="Policy pack template to write as policy.yaml.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
) -> None:
    """Write lexshield.yaml, policy.yaml, rules.yaml, and .gitignore entries."""
    cwd = Path.cwd()
    _write_file(cwd / "lexshield.yaml", LEXSHIELD_YAML, force=force)

    policy_content = POLICY_TEMPLATES[pack]
    if pack == "baseline-deny":
        policy_content = _ensure_baseline_challenge_delete(policy_content)
    _write_file(cwd / "policy.yaml", policy_content, force=force)

    _write_rules_from_pack(cwd, pack, force=force)
    _ensure_gitignore(cwd)
    console.print(f"[bold green]LexShield initialized[/bold green] (pack: {pack})")
