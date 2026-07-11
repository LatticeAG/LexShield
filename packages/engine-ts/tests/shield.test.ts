import { describe, expect, it } from 'vitest';

import { LexShieldBlockedError } from '../src/errors.js';
import { Shield } from '../src/shield.js';
import type { Policy } from '../src/types.js';

const baselinePolicy: Policy = {
  id: 'baseline-deny',
  name: 'Baseline default-deny',
  version: '1',
  defaultVerdict: 'BLOCK',
  rules: [
    {
      id: 'allow-health',
      name: 'Allow health checks',
      priority: 100,
      match: {
        tools: ['health_check', 'ping'],
        intents: ['network.request.health'],
      },
      verdict: 'ALLOW',
      reason: 'Health checks are always allowed',
    },
    {
      id: 'block-secret-exposure',
      name: 'Block secret exposure',
      priority: 300,
      match: {
        intents: ['security.secret_exposure'],
      },
      verdict: 'BLOCK',
      reason: 'Possible secret exposure in tool arguments',
    },
  ],
};

const deterministicRules = {
  version: '1',
  tool_map: {
    health_check: 'network.request.health',
    send_email: 'comms.send.email',
  },
  patterns: [
    {
      name: 'aws_access_key',
      match: {
        any_arg_regex: 'AKIA[0-9A-Z]{16}',
      },
      intent: 'security.secret_exposure',
      confidence: 0.98,
    },
  ],
};

function createShield(policy: Policy = baselinePolicy): Shield {
  return Shield.fromOptions({
    config: {
      version: '1',
      shield: {
        id: 'local',
        name: 'test-shield',
        policy: './policy.yaml',
        classifiers: [{ type: 'deterministic', path: './rules.yaml' }],
        sinks: [],
      },
    },
    policy,
    deterministicRules,
  });
}

describe('Shield', () => {
  it('allows health checks under default-deny policy', async () => {
    const shield = createShield();
    const verdict = await shield.evaluate({ tool: 'health_check' });

    expect(verdict.decision).toBe('ALLOW');
    expect(verdict.matchedRuleId).toBe('allow-health');
  });

  it('blocks secret exposure detected by deterministic patterns', async () => {
    const shield = createShield();
    const verdict = await shield.evaluate({
      tool: 'send_email',
      arguments: {
        to: 'ops@example.com',
        body: 'key AKIAIOSFODNN7EXAMPLE',
      },
    });

    expect(verdict.decision).toBe('BLOCK');
    expect(verdict.matchedRuleId).toBe('block-secret-exposure');
    expect(verdict.classifications[0]?.intent).toBe('security.secret_exposure');
  });

  it('guard raises on BLOCK and runs wrapped function on ALLOW', async () => {
    const shield = createShield();
    const guarded = shield.guard('health_check', async () => 'ok');

    await expect(guarded({})).resolves.toBe('ok');

    const blocked = shield.guard('send_email', async () => 'sent');
    await expect(
      blocked({ body: 'AKIAIOSFODNN7EXAMPLE' }),
    ).rejects.toBeInstanceOf(LexShieldBlockedError);
  });
});
