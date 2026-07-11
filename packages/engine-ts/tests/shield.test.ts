import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import { describe, expect, it, afterEach } from 'vitest';

import { ChallengeStore } from '../src/challenges/store.js';
import { ClassifierPipeline } from '../src/classifiers/pipeline.js';
import {
  LexShieldBlockedError,
  LexShieldChallengeError,
} from '../src/errors.js';
import { Shield } from '../src/shield.js';
import { NDJSONTraceSink } from '../src/traces/sink.js';
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
    {
      id: 'challenge-delete-prod',
      name: 'Challenge destructive infra in production',
      priority: 200,
      match: {
        environments: ['production'],
        intents: ['infra.delete.resource', 'data.delete.record'],
      },
      verdict: 'CHALLENGE',
      reason: 'Destructive action in production requires approval',
    },
  ],
};

const deterministicRules = {
  version: '1',
  tool_map: {
    health_check: 'network.request.health',
    send_email: 'comms.send.email',
    delete_resource: 'infra.delete.resource',
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

const tempDirs: string[] = [];

afterEach(() => {
  for (const dir of tempDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

function makeTempDir(): string {
  const dir = mkdtempSync(join(tmpdir(), 'lexshield-shield-'));
  tempDirs.push(dir);
  return dir;
}

function createShield(policy: Policy = baselinePolicy, traceSinkPath?: string): Shield {
  const traceSink = traceSinkPath ? new NDJSONTraceSink(traceSinkPath) : null;

  return Shield.fromOptions({
    config: {
      version: '1',
      shield: {
        id: 'local',
        name: 'test-shield',
        policy: './policy.yaml',
        classifiers: [{ type: 'deterministic', path: './rules.yaml' }],
        sinks: traceSinkPath ? [{ type: 'file', path: './traces.ndjson', options: {} }] : [],
      },
    },
    policy,
    policyPath: './policy.yaml',
    classifierPipeline: new ClassifierPipeline({
      deterministicRules,
      llmEnabled: false,
    }),
    traceSink,
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

  it('guardSync evaluates synchronously for deterministic paths', () => {
    const shield = createShield();
    const guarded = shield.guardSync('health_check', () => 'ok');

    expect(guarded({})).toBe('ok');

    const blocked = shield.guardSync('send_email', () => 'sent');
    expect(() => blocked({ body: 'AKIAIOSFODNN7EXAMPLE' })).toThrow(LexShieldBlockedError);
  });

  it('applies session context from ShieldSession', async () => {
    const shield = createShield();
    const session = shield.session({ environment: 'production' });

    const verdict = await session.runAsync(() =>
      shield.evaluate({ tool: 'delete_resource' }),
    );

    expect(verdict.decision).toBe('CHALLENGE');
    expect(verdict.matchedRuleId).toBe('challenge-delete-prod');
  });

  it('writes traces to NDJSON sink on evaluate', async () => {
    const dir = makeTempDir();
    const tracePath = join(dir, 'traces.ndjson');
    const shield = createShield(baselinePolicy, tracePath);

    const verdict = await shield.evaluate({
      tool: 'health_check',
      requestId: 'trace-req-1',
    });

    const lines = readFileSync(tracePath, 'utf8').trim().split('\n');
    expect(lines).toHaveLength(1);

    const trace = JSON.parse(lines[0]!);
    expect(trace.id).toBe('trace-req-1');
    expect(trace.verdict.decision).toBe(verdict.decision);
  });

  it('records outcomes via trace sink updateOutcome', async () => {
    const dir = makeTempDir();
    const tracePath = join(dir, 'traces.ndjson');
    const shield = createShield(baselinePolicy, tracePath);

    await shield.evaluate({
      tool: 'health_check',
      requestId: 'trace-req-2',
    });

    await shield.recordOutcome('trace-req-2', 'EXECUTED');

    const trace = JSON.parse(readFileSync(tracePath, 'utf8').trim());
    expect(trace.outcome).toBe('EXECUTED');
    expect(trace.outcomeAt).toBeTruthy();
  });

  it('loads shield config from yaml via fromConfig', async () => {
    const dir = makeTempDir();

    writeFileSync(
      join(dir, 'policy.yaml'),
      `id: test-policy
name: Test Policy
version: 1
defaultVerdict: BLOCK
rules:
  - id: allow-health
    name: Allow health
    priority: 100
    match:
      tools: [health_check]
      intents: [network.request.health]
    verdict: ALLOW
    reason: Health checks are always allowed
`,
      'utf8',
    );

    writeFileSync(
      join(dir, 'rules.yaml'),
      `version: 1
tool_map:
  health_check: network.request.health
patterns: []
`,
      'utf8',
    );

    writeFileSync(
      join(dir, 'lexshield.yaml'),
      `version: 1
shield:
  id: local
  name: test-shield
  policy: ./policy.yaml
  classifiers:
    - type: deterministic
      path: ./rules.yaml
  sinks:
    - type: file
      path: ./traces.ndjson
`,
      'utf8',
    );

    const shield = await Shield.fromConfig(join(dir, 'lexshield.yaml'));
    const verdict = await shield.evaluate({ tool: 'health_check' });

    expect(verdict.decision).toBe('ALLOW');
    expect(shield.traceSink).not.toBeNull();
  });

  it('raises LexShieldChallengeError from guard on CHALLENGE', async () => {
    const shield = createShield();
    const guarded = shield.guard('delete_resource', async () => 'deleted');

    await expect(
      shield.session({ environment: 'production' }).runAsync(() => guarded({})),
    ).rejects.toBeInstanceOf(LexShieldChallengeError);
  });
});

describe('ChallengeStore', () => {
  it('creates, lists, and resolves challenges', () => {
    const dir = makeTempDir();
    const store = new ChallengeStore(join(dir, 'challenges'));

    const challengeId = store.create({
      requestId: 'req-123',
      reason: 'Needs approval',
    });

    expect(challengeId).toBeTruthy();
    expect(store.listOpen()).toHaveLength(1);

    const resolved = store.resolve(challengeId, {
      decision: 'approve',
      actor: 'reviewer@example.com',
    });

    expect(resolved?.status).toBe('approved');
    expect(store.listOpen()).toHaveLength(0);
  });
});
