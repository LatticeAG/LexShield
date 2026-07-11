import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { evaluatePolicy } from '../src/policy/engine.js';
import { Expression, ExpressionError, buildExpressionBindings } from '../src/policy/expressions.js';
import { loadPolicyFromFile } from '../src/policy/loader.js';
import type { Classification, Policy, ToolCallRequest } from '../src/types.js';

const workspaceRoot = resolve(fileURLToPath(new URL('../../..', import.meta.url)));
const baselinePolicyPath = resolve(workspaceRoot, 'packs/baseline-deny/policy.yaml');

function classification(
  intent: string,
  confidence = 0.9,
  alternatives: Array<{ intent: string; confidence: number }> = [],
): Classification {
  return {
    intent,
    confidence,
    alternatives,
    classifier: 'test',
  };
}

function request(options: {
  tool?: string;
  arguments?: Record<string, unknown>;
  environment?: string;
  tags?: Record<string, string>;
  callerId?: string;
  callerRoles?: string[];
} = {}): ToolCallRequest {
  return {
    id: '01JTEST',
    shieldId: 'local',
    timestamp: '2026-07-11T12:00:00.000Z',
    caller: {
      id: options.callerId ?? 'agent-1',
      type: 'agent',
      roles: options.callerRoles,
    },
    tool: { name: options.tool ?? 'health_check' },
    arguments: options.arguments ?? {},
    context: {
      environment: options.environment,
      tags: options.tags,
    },
  };
}

async function loadBaselinePolicy(): Promise<Policy> {
  return loadPolicyFromFile(baselinePolicyPath);
}

describe('evaluatePolicy', () => {
  it('allows health checks', async () => {
    const policy = await loadBaselinePolicy();
    const verdict = evaluatePolicy(policy, {
      request: request({ tool: 'health_check' }),
      classifications: [classification('network.request.health')],
    });

    expect(verdict.decision).toBe('ALLOW');
    expect(verdict.matchedRuleId).toBe('allow-health');
    expect(verdict.reason).toBe('Health checks are always allowed');
  });

  it('blocks secret exposure', async () => {
    const policy = await loadBaselinePolicy();
    const verdict = evaluatePolicy(policy, {
      request: request({
        tool: 'send_email',
        arguments: { body: 'AKIAIOSFODNN7EXAMPLE' },
      }),
      classifications: [classification('security.secret_exposure', 0.98)],
    });

    expect(verdict.decision).toBe('BLOCK');
    expect(verdict.matchedRuleId).toBe('block-secret-exposure');
    expect(verdict.reason).toBe('Possible secret exposure in tool arguments');
  });

  it('challenges destructive actions in production', async () => {
    const policy = await loadBaselinePolicy();
    const verdict = evaluatePolicy(policy, {
      request: request({
        tool: 'delete_resource',
        environment: 'production',
      }),
      classifications: [classification('infra.delete.resource', 0.95)],
    });

    expect(verdict.decision).toBe('CHALLENGE');
    expect(verdict.matchedRuleId).toBe('challenge-delete-prod');
    expect(verdict.reason).toBe('Destructive action in production requires approval');
    expect(verdict.challengeId).toBe('challenge-01JTEST');
  });

  it('tie-breaks equal priority by rule id ascending', () => {
    const policy: Policy = {
      id: 'tie-break',
      name: 'Tie break',
      version: '1',
      defaultVerdict: 'BLOCK',
      rules: [
        {
          id: 'rule-b',
          name: 'Rule B',
          priority: 300,
          match: { intents: ['security.secret_exposure'] },
          verdict: 'BLOCK',
          reason: 'Blocked by rule-b',
        },
        {
          id: 'rule-a',
          name: 'Rule A',
          priority: 300,
          match: { intents: ['security.secret_exposure'] },
          verdict: 'ALLOW',
          reason: 'Allowed by rule-a',
        },
      ],
    };

    const verdict = evaluatePolicy(policy, {
      request: request({ tool: 'send_email' }),
      classifications: [classification('security.secret_exposure')],
    });

    expect(verdict.decision).toBe('ALLOW');
    expect(verdict.matchedRuleId).toBe('rule-a');
  });

  it('denies unclassified intents when no rule matches', async () => {
    const policy = await loadBaselinePolicy();
    const verdict = evaluatePolicy(policy, {
      request: request({ tool: 'unknown_tool' }),
      classifications: [classification('unknown.unclassified', 0.2)],
    });

    expect(verdict.decision).toBe('BLOCK');
    expect(verdict.matchedRuleId).toBeUndefined();
    expect(verdict.reason).toBe(
      'No matching policy rule; default deny for unclassified intent',
    );
  });

  it('matches tool globs', () => {
    const policy: Policy = {
      id: 'glob-tools',
      name: 'Glob tools',
      version: '1',
      defaultVerdict: 'BLOCK',
      rules: [
        {
          id: 'allow-send',
          name: 'Allow send tools',
          priority: 100,
          match: {
            tools: ['send_*'],
            intents: ['comms.send.email'],
          },
          verdict: 'ALLOW',
          reason: 'Send tools allowed',
        },
      ],
    };

    const verdict = evaluatePolicy(policy, {
      request: request({ tool: 'send_email' }),
      classifications: [classification('comms.send.email')],
    });

    expect(verdict.decision).toBe('ALLOW');
    expect(verdict.matchedRuleId).toBe('allow-send');
  });

  it('requires all configured tags', () => {
    const policy: Policy = {
      id: 'tag-policy',
      name: 'Tag policy',
      version: '1',
      defaultVerdict: 'BLOCK',
      rules: [
        {
          id: 'challenge-pii',
          name: 'Challenge PII',
          priority: 200,
          match: {
            intents: ['comms.send.email'],
            tags: { data_class: ['pii'], region: ['us'] },
          },
          verdict: 'CHALLENGE',
          reason: 'PII egress requires approval',
        },
      ],
    };

    const blocked = evaluatePolicy(policy, {
      request: request({
        tool: 'send_email',
        tags: { data_class: 'pii' },
      }),
      classifications: [classification('comms.send.email')],
    });
    expect(blocked.decision).toBe('BLOCK');
    expect(blocked.matchedRuleId).toBeUndefined();

    const challenged = evaluatePolicy(policy, {
      request: request({
        tool: 'send_email',
        tags: { data_class: 'pii', region: 'us' },
      }),
      classifications: [classification('comms.send.email')],
    });
    expect(challenged.decision).toBe('CHALLENGE');
    expect(challenged.matchedRuleId).toBe('challenge-pii');
  });

  it('evaluates expressions for block and allow rules', () => {
    const policy: Policy = {
      id: 'expr-policy',
      name: 'Expression policy',
      version: '1',
      defaultVerdict: 'BLOCK',
      rules: [
        {
          id: 'block-gmail',
          name: 'Block gmail recipients',
          priority: 250,
          match: {
            intents: ['comms.send.email'],
            expression: 'env == "production" && args.to contains "@gmail.com"',
          },
          verdict: 'BLOCK',
          reason: 'Gmail not allowed in production',
        },
        {
          id: 'allow-allowlisted-url',
          name: 'Allow allowlisted URL',
          priority: 200,
          match: {
            intents: ['network.request.http'],
            expression: 'args.url startsWith "https://api.mycompany.com/"',
          },
          verdict: 'ALLOW',
          reason: 'Allowlisted host',
        },
      ],
    };

    const blocked = evaluatePolicy(policy, {
      request: request({
        tool: 'send_email',
        arguments: { to: 'user@gmail.com' },
        environment: 'production',
      }),
      classifications: [classification('comms.send.email')],
    });
    expect(blocked.decision).toBe('BLOCK');
    expect(blocked.matchedRuleId).toBe('block-gmail');

    const allowed = evaluatePolicy(policy, {
      request: request({
        tool: 'http_request',
        arguments: { url: 'https://api.mycompany.com/v1/data' },
      }),
      classifications: [classification('network.request.http')],
    });
    expect(allowed.decision).toBe('ALLOW');
    expect(allowed.matchedRuleId).toBe('allow-allowlisted-url');
  });

  it('matches alternative intents on the primary classification', () => {
    const policy: Policy = {
      id: 'alt-intent',
      name: 'Alt intent',
      version: '1',
      defaultVerdict: 'BLOCK',
      rules: [
        {
          id: 'allow-alt',
          name: 'Allow alt',
          priority: 100,
          match: { intents: ['data.exfiltrate'] },
          verdict: 'BLOCK',
          reason: 'Blocked exfil',
        },
      ],
    };

    const verdict = evaluatePolicy(policy, {
      request: request({ tool: 'http_request' }),
      classifications: [
        classification('network.request.http', 0.6, [
          { intent: 'data.exfiltrate', confidence: 0.4 },
        ]),
      ],
    });

    expect(verdict.decision).toBe('BLOCK');
    expect(verdict.matchedRuleId).toBe('allow-alt');
  });

  it('skips disabled rules', () => {
    const policy: Policy = {
      id: 'disabled',
      name: 'Disabled',
      version: '1',
      defaultVerdict: 'ALLOW',
      rules: [
        {
          id: 'disabled-block',
          name: 'Disabled block',
          priority: 500,
          enabled: false,
          match: { tools: ['health_check'] },
          verdict: 'BLOCK',
          reason: 'Would block',
        },
      ],
    };

    const verdict = evaluatePolicy(policy, {
      request: request({ tool: 'health_check' }),
      classifications: [classification('network.request.health')],
    });

    expect(verdict.decision).toBe('ALLOW');
    expect(verdict.matchedRuleId).toBeUndefined();
  });

  it('applies default verdict for classified requests with no rule match', async () => {
    const policy = await loadBaselinePolicy();
    const verdict = evaluatePolicy(policy, {
      request: request({ tool: 'send_email' }),
      classifications: [classification('comms.send.email', 0.7)],
    });

    expect(verdict.decision).toBe('BLOCK');
    expect(verdict.matchedRuleId).toBeUndefined();
    expect(verdict.reason).toBe('No matching rule; applied default verdict BLOCK');
  });
});

describe('Expression', () => {
  it('rejects empty expressions', () => {
    expect(() => Expression.parse('   ')).toThrow(ExpressionError);
  });

  it('supports the in operator', () => {
    const expr = Expression.parse('intent in ["comms.send.email", "comms.send.slack"]');
    const bindings = {
      intent: 'comms.send.email',
      confidence: 0.9,
      'tool.name': 'send_email',
      'caller.id': 'agent-1',
      'caller.type': 'agent',
      env: 'staging',
    };

    expect(expr.evaluate(bindings)).toBe(true);
  });

  it('supports numeric comparison bindings', () => {
    const expr = Expression.parse('confidence >= 0.7');
    const bindings = buildExpressionBindings(request(), [classification('network.request.health', 0.75)]);
    expect(expr.evaluate(bindings)).toBe(true);
  });
});
