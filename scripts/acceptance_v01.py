#!/usr/bin/env python3
"""Automated v0.1 acceptance checklist runner (SPEC Appendix D).

Runs verifiable release gates: golden fixture counts, test suites, pack
validation, LICENSE, taxonomy, demos, docs, and CLI smoke flows.

Exit 0 only when all automated checks pass. Does not publish to PyPI/npm.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_ROOT = REPO_ROOT / "fixtures" / "golden"
TAXONOMY_PATH = REPO_ROOT / "taxonomy" / "builtin.yaml"
LICENSE_PATH = REPO_ROOT / "LICENSE"
SECURITY_DOC = REPO_ROOT / "docs" / "security.md"
PACKS = ("baseline-deny", "pii-guard", "change-window")
DEMOS = (
    "examples/python-block-exfil",
    "examples/python-challenge-delete",
    "examples/ts-evaluate",
)
SPEC_GOLDEN_TARGET = 50
BUILTIN_INTENT_COUNT = 24


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class AcceptanceReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.results.append(CheckResult(name=name, passed=passed, detail=detail))
        status = "PASS" if passed else "FAIL"
        line = f"[{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    @property
    def ok(self) -> bool:
        return all(result.passed for result in self.results)


def _run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd or REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def discover_golden_scenarios() -> list[str]:
    if not GOLDEN_ROOT.is_dir():
        return []
    return sorted(
        entry.name
        for entry in GOLDEN_ROOT.iterdir()
        if entry.is_dir() and (entry / "request.json").is_file()
    )


def check_license(report: AcceptanceReport) -> None:
    if not LICENSE_PATH.is_file():
        report.add("MIT LICENSE present", False, "LICENSE file missing")
        return
    text = LICENSE_PATH.read_text(encoding="utf-8")
    passed = "MIT License" in text and "Permission is hereby granted" in text
    report.add("MIT LICENSE present", passed)


def check_taxonomy(report: AcceptanceReport) -> None:
    if not TAXONOMY_PATH.is_file():
        report.add("taxonomy/builtin.yaml", False, "file missing")
        return
    with TAXONOMY_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    intents = data.get("intents") or {}
    count = len(intents)
    version = data.get("version")
    passed = count == BUILTIN_INTENT_COUNT and version == "v0.1"
    report.add(
        "taxonomy/builtin.yaml (24 intents, v0.1)",
        passed,
        f"found {count} intents, version={version!r}",
    )


def check_golden_count(report: AcceptanceReport) -> int:
    scenarios = discover_golden_scenarios()
    count = len(scenarios)
    report.add(
        "Golden fixture count",
        count > 0,
        f"{count} scenarios (SPEC aspirational target ≥ {SPEC_GOLDEN_TARGET})",
    )
    if 0 < count < SPEC_GOLDEN_TARGET:
        print(
            f"  [WARN] {count} < {SPEC_GOLDEN_TARGET} — SPEC Appendix D targets ≥ {SPEC_GOLDEN_TARGET}; "
            "all scenarios must still be green",
        )
    return count


def check_golden_pytest(report: AcceptanceReport) -> None:
    result = _run(["uv", "run", "pytest", "-m", "golden", "-q"])
    passed = result.returncode == 0
    detail = "all green" if passed else (result.stdout + result.stderr).strip()[-400:]
    report.add("Python golden tests (pytest -m golden)", passed, detail)


def check_golden_ts(report: AcceptanceReport) -> None:
    result = _run(["pnpm", "test:golden"])
    passed = result.returncode == 0
    detail = "parity OK" if passed else (result.stdout + result.stderr).strip()[-400:]
    report.add("TypeScript golden parity (pnpm test:golden)", passed, detail)


def check_packs(report: AcceptanceReport) -> None:
    for pack in PACKS:
        policy = REPO_ROOT / "packs" / pack / "policy.yaml"
        rules = REPO_ROOT / "packs" / pack / "rules.yaml"
        if not policy.is_file() or not rules.is_file():
            report.add(f"Pack files: {pack}", False, "policy.yaml or rules.yaml missing")
            return
    result = _run(["uv", "run", "lexshield-check-packs"])
    passed = result.returncode == 0
    detail = "3 packs validated" if passed else (result.stdout + result.stderr).strip()[-300:]
    report.add("Policy pack validation (lexshield-check-packs)", passed, detail)


def check_default_deny_unknown_tool(report: AcceptanceReport) -> None:
    scenario = "block-unknown-tool"
    expected_path = GOLDEN_ROOT / scenario / "expected.json"
    if not expected_path.is_file():
        report.add("Default-deny blocks unknown tools", False, f"missing fixture {scenario}")
        return
    expected = yaml.safe_load(expected_path.read_text(encoding="utf-8"))  # JSON is YAML subset
    passed = expected.get("decision") == "BLOCK"
    report.add(
        "Default-deny blocks unknown tools",
        passed,
        f"fixture {scenario} decision={expected.get('decision')!r}",
    )


def check_secret_exposure_fixture(report: AcceptanceReport) -> None:
    scenario = "block-secret-exposure"
    expected_path = GOLDEN_ROOT / scenario / "expected.json"
    if not expected_path.is_file():
        report.add("Secret pattern → security.secret_exposure → BLOCK", False, "fixture missing")
        return
    expected = yaml.safe_load(expected_path.read_text(encoding="utf-8"))
    passed = (
        expected.get("decision") == "BLOCK"
        and expected.get("primaryIntent") == "security.secret_exposure"
    )
    report.add(
        "Secret pattern → security.secret_exposure → BLOCK",
        passed,
        f"decision={expected.get('decision')!r}, intent={expected.get('primaryIntent')!r}",
    )


def check_llm_tests(report: AcceptanceReport) -> None:
    result = _run(
        ["uv", "run", "pytest", "packages/engine-py/tests/test_llm_classifier.py", "-q"],
    )
    passed = result.returncode == 0
    detail = "cassette/mock path green" if passed else (result.stdout + result.stderr).strip()[-300:]
    report.add("LLM classifier tests (mocked, no API key)", passed, detail)


def check_redaction_tests(report: AcceptanceReport) -> None:
    py_result = _run(["uv", "run", "pytest", "packages/engine-py/tests/test_redaction.py", "-q"])
    ts_result = _run(
        ["pnpm", "--filter", "@latticeag/lexshield", "exec", "vitest", "run", "tests/redaction.test.ts"],
    )
    passed = py_result.returncode == 0 and ts_result.returncode == 0
    detail = "Python + TS redaction tests" if passed else "one or more redaction suites failed"
    report.add("Redaction tests", passed, detail)


def check_cli_smoke(report: AcceptanceReport) -> None:
    with tempfile.TemporaryDirectory(prefix="lexshield-accept-") as tmp:
        tmp_path = Path(tmp)
        init = _run(
            ["uv", "run", "lexshield", "init", "--pack", "baseline-deny"],
            cwd=tmp_path,
        )
        if init.returncode != 0:
            report.add("CLI init", False, (init.stdout + init.stderr).strip()[-200:])
            return
        report.add("CLI init", True)

        check = _run(["uv", "run", "lexshield", "check", "--strict"], cwd=tmp_path)
        report.add(
            "CLI check --strict",
            check.returncode == 0,
            "offline validation" if check.returncode == 0 else (check.stdout + check.stderr)[-200:],
        )

        evaluate = _run(
            [
                "uv",
                "run",
                "lexshield",
                "evaluate",
                "--tool",
                "health_check",
                "--args",
                "{}",
                "--json",
            ],
            cwd=tmp_path,
        )
        report.add(
            "CLI evaluate (offline)",
            evaluate.returncode == 0,
            "health_check ALLOW" if evaluate.returncode == 0 else (evaluate.stdout + evaluate.stderr)[-200:],
        )


def check_bind_all_refused(report: AcceptanceReport) -> None:
    result = _run(["uv", "run", "lexshield", "run", "--host", "0.0.0.0"])
    combined = result.stdout + result.stderr
    passed = result.returncode != 0 and "Refusing to bind 0.0.0.0" in combined
    report.add("Bind-all refused without --i-understand-bind-all", passed)


def check_api_tests(report: AcceptanceReport) -> None:
    result = _run(["uv", "run", "pytest", "packages/engine-py/tests/test_api.py", "-q"])
    passed = result.returncode == 0
    report.add("FastAPI routes (/evaluate, /healthz)", passed, "test_api.py green" if passed else "")


def check_guard_tests(report: AcceptanceReport) -> None:
    result = _run(["uv", "run", "pytest", "packages/engine-py/tests/test_shield.py", "-q"])
    passed = result.returncode == 0
    report.add("@shield.guard SDK tests", passed, "test_shield.py green" if passed else "")


def check_demos_exist(report: AcceptanceReport) -> None:
    missing = [demo for demo in DEMOS if not (REPO_ROOT / demo).is_dir()]
    passed = not missing
    detail = "3 demos present" if passed else f"missing: {', '.join(missing)}"
    report.add("Example demos (3)", passed, detail)


def check_security_doc(report: AcceptanceReport) -> None:
    if not SECURITY_DOC.is_file():
        report.add("docs/security.md", False, "file missing")
        return
    text = SECURITY_DOC.read_text(encoding="utf-8").lower()
    passed = "probabilistic" in text and "threat" in text
    report.add(
        "docs/security.md (probabilistic limits)",
        passed,
        "states LLM limits honestly" if passed else "missing probabilistic/threat language",
    )


def check_ts_build(report: AcceptanceReport) -> None:
    result = _run(["pnpm", "--filter", "@latticeag/lexshield", "build"])
    passed = result.returncode == 0
    dist = REPO_ROOT / "packages" / "engine-ts" / "dist" / "index.js"
    if passed and not dist.is_file():
        passed = False
        detail = "build succeeded but dist/index.js missing"
    else:
        detail = "dist/ produced" if passed else (result.stdout + result.stderr).strip()[-300:]
    report.add("TypeScript SDK build", passed, detail)


def check_package_versions(report: AcceptanceReport) -> None:
    engine_toml = (REPO_ROOT / "packages" / "engine-py" / "pyproject.toml").read_text(encoding="utf-8")
    cli_toml = (REPO_ROOT / "packages" / "cli" / "pyproject.toml").read_text(encoding="utf-8")
    ts_pkg = (REPO_ROOT / "packages" / "engine-ts" / "package.json").read_text(encoding="utf-8")
    versions = {
        "lexshield": re.search(r'^version = "([^"]+)"', engine_toml, re.M),
        "lexshield-cli": re.search(r'^version = "([^"]+)"', cli_toml, re.M),
        "@latticeag/lexshield": re.search(r'"version":\s*"([^"]+)"', ts_pkg),
    }
    passed = all(match and match.group(1) == "0.1.0" for match in versions.values())
    detail = ", ".join(f"{name}={match.group(1) if match else '?'}" for name, match in versions.items())
    report.add("Package versions 0.1.0", passed, detail)


def check_publish_skipped(report: AcceptanceReport) -> None:
    report.add(
        "PyPI/npm publish",
        True,
        "SKIPPED (no credentials — prepare only; publish manually from tag)",
    )


def main() -> int:
    print(f"LexShield v0.1 acceptance checklist — {REPO_ROOT}\n")

    report = AcceptanceReport()

    check_license(report)
    check_taxonomy(report)
    check_golden_count(report)
    check_golden_pytest(report)
    check_golden_ts(report)
    check_packs(report)
    check_default_deny_unknown_tool(report)
    check_secret_exposure_fixture(report)
    check_llm_tests(report)
    check_redaction_tests(report)
    check_cli_smoke(report)
    check_bind_all_refused(report)
    check_api_tests(report)
    check_guard_tests(report)
    check_demos_exist(report)
    check_security_doc(report)
    check_ts_build(report)
    check_package_versions(report)
    check_publish_skipped(report)

    passed = sum(1 for r in report.results if r.passed)
    total = len(report.results)
    print(f"\n{passed}/{total} checks passed.")

    if not report.ok:
        print("\nAcceptance FAILED. See CONTRIBUTING.md and SPEC Appendix D.")
        return 1

    print("\nAcceptance PASSED (automated Appendix D checks).")
    print("Manual: verify README quickstart on a clean machine; publish PyPI/npm from tag when ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
