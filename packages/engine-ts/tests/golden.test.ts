import { access, readdir, readFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { parse as parseYaml } from 'yaml';
import { describe, expect, it } from 'vitest';

import { classifyDeterministic, loadDeterministicRulesFromFile } from '../src/classifiers/deterministic.js';
import { evaluatePolicy } from '../src/policy/engine.js';
import { loadPolicyFromData, loadPolicyFromFile } from '../src/policy/loader.js';
import { ToolCallRequestSchema, type Policy, type ToolCallRequest } from '../src/types.js';

const workspaceRoot = resolve(fileURLToPath(new URL('../../..', import.meta.url)));
const fixturesRoot = join(workspaceRoot, 'fixtures', 'golden');
const UNKNOWN_INTENT = 'unknown.unclassified';

interface PolicyRef {
  pack?: string;
  policy: string | Record<string, unknown>;
  rules?: string;
}

interface GoldenExpected {
  decision: string;
  matchedRuleId?: string | null;
  reason: string;
  primaryIntent?: string;
  strict?: boolean;
}

async function listGoldenScenarios(): Promise<string[]> {
  const entries = await readdir(fixturesRoot, { withFileTypes: true });
  const scenarios: string[] = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }
    try {
      await access(join(fixturesRoot, entry.name, 'request.json'));
      scenarios.push(entry.name);
    } catch {
      // skip directories without request.json
    }
  }

  return scenarios.sort();
}

function resolveFixturePath(baseDir: string, value: string): string {
  const path = value.startsWith('/') ? value : resolve(baseDir, value);
  return path;
}

async function loadPolicyRef(scenarioDir: string): Promise<{
  policy: Policy;
  rulesPath: string | null;
}> {
  const policyRefRaw = await readFile(join(scenarioDir, 'policy-ref.yaml'), 'utf8');
  const policyRef = parseYaml(policyRefRaw) as PolicyRef;

  let policy: Policy;
  if (typeof policyRef.policy === 'object' && policyRef.policy !== null) {
    policy = loadPolicyFromData(policyRef.policy, join(scenarioDir, 'policy-ref.yaml'));
  } else if (typeof policyRef.policy === 'string') {
    policy = await loadPolicyFromFile(resolveFixturePath(scenarioDir, policyRef.policy));
  } else if (policyRef.pack) {
    policy = await loadPolicyFromFile(join(workspaceRoot, 'packs', policyRef.pack, 'policy.yaml'));
  } else {
    throw new Error(`policy-ref.yaml in ${scenarioDir} must define policy or pack`);
  }

  let rulesPath: string | null = null;
  if (typeof policyRef.rules === 'string') {
    rulesPath = resolveFixturePath(scenarioDir, policyRef.rules);
  } else {
    const rulesRefPath = join(scenarioDir, 'rules-ref.yaml');
    try {
      await readFile(rulesRefPath, 'utf8');
      rulesPath = rulesRefPath;
    } catch {
      if (policyRef.pack) {
        rulesPath = join(workspaceRoot, 'packs', policyRef.pack, 'rules.yaml');
      }
    }
  }

  return { policy, rulesPath };
}

async function classificationsForRequest(
  request: ToolCallRequest,
  rulesPath: string | null,
) {
  if (!rulesPath) {
    return [
      {
        intent: UNKNOWN_INTENT,
        confidence: 0.3,
        alternatives: [],
        classifier: 'deterministic:v1',
        reasoning: 'No deterministic classification',
      },
    ];
  }

  const rules = await loadDeterministicRulesFromFile(rulesPath);
  const result = classifyDeterministic(request, { rules });
  if (result) {
    return [result];
  }

  return [
    {
      intent: UNKNOWN_INTENT,
      confidence: 0.3,
      alternatives: [],
      classifier: 'deterministic:v1',
      reasoning: 'No deterministic classification',
    },
  ];
}

async function loadGoldenScenario(scenario: string) {
  const scenarioDir = join(fixturesRoot, scenario);
  const requestRaw = await readFile(join(scenarioDir, 'request.json'), 'utf8');
  const expectedRaw = await readFile(join(scenarioDir, 'expected.json'), 'utf8');

  const request = ToolCallRequestSchema.parse(JSON.parse(requestRaw));
  const expected = JSON.parse(expectedRaw) as GoldenExpected;
  const strict = Boolean(expected.strict);
  delete expected.strict;

  const { policy, rulesPath } = await loadPolicyRef(scenarioDir);
  const classifications = await classificationsForRequest(request, rulesPath);
  const verdict = evaluatePolicy(policy, { request, classifications });

  return {
    scenario,
    expected,
    verdict,
    primaryIntent: classifications[0]?.intent,
    strict,
  };
}

describe('golden fixtures', () => {
  it('discovers fixture scenarios', async () => {
    const scenarios = await listGoldenScenarios();
    expect(scenarios.length).toBeGreaterThan(0);
  });

  it('matches Python verdicts for all fixtures', async () => {
    const scenarios = await listGoldenScenarios();

    for (const scenario of scenarios) {
      const result = await loadGoldenScenario(scenario);

      expect(result.verdict.decision, `${scenario} decision`).toBe(result.expected.decision);
      expect(result.verdict.reason, `${scenario} reason`).toBe(result.expected.reason);

      if ('matchedRuleId' in result.expected) {
        expect(result.verdict.matchedRuleId, `${scenario} matchedRuleId`).toBe(
          result.expected.matchedRuleId ?? undefined,
        );
      }

      if (result.expected.primaryIntent !== undefined) {
        expect(result.primaryIntent, `${scenario} primaryIntent`).toBe(
          result.expected.primaryIntent,
        );
      }
    }
  });
});
