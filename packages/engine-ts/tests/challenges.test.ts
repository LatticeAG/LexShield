import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import { afterEach, describe, expect, it } from 'vitest';

import { LLMCircuitBreaker } from '../src/classifiers/circuit-breaker.js';
import { LLMClassifier } from '../src/classifiers/llm.js';
import {
  ClassifierPipeline,
  clearClassificationCache,
} from '../src/classifiers/pipeline.js';
import type { ToolCallRequest } from '../src/types.js';

const deterministicRules = {
  version: '1',
  tool_map: {
    send_email: 'comms.send.email',
  },
  patterns: [],
};

function request(): ToolCallRequest {
  return {
    id: 'req-1',
    shieldId: 'local',
    timestamp: '2026-07-11T12:00:00.000Z',
    caller: { id: 'agent-1', type: 'agent' },
    tool: { name: 'send_email' },
    arguments: { body: 'hello' },
    context: {},
  };
}

const tempDirs: string[] = [];

afterEach(() => {
  clearClassificationCache();
  for (const dir of tempDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

function makeTempDir(): string {
  const dir = mkdtempSync(join(tmpdir(), 'lexshield-store-'));
  tempDirs.push(dir);
  return dir;
}

describe('ClassifierPipeline circuit breaker', () => {
  it('skips LLM when circuit is open', async () => {
    const circuitBreaker = new LLMCircuitBreaker({ failureThreshold: 1 });
    circuitBreaker.recordFailure();

    const llm = new LLMClassifier({
      classifyFn: async () => {
        throw new Error('LLM should not be called');
      },
    });

    const pipeline = new ClassifierPipeline({
      deterministicRules,
      llm,
      circuitBreaker,
    });

    const result = await pipeline.classify(request());
    expect(result[0]?.intent).toBe('comms.send.email');
  });
});

describe('ChallengeStore expireOpen', () => {
  it('resolves timed-out open challenges based on onTimeout', async () => {
    const { ChallengeStore } = await import('../src/challenges/store.js');
    const store = new ChallengeStore(join(makeTempDir(), 'challenges'));

    const challengeId = store.create({
      requestId: 'req-timeout',
      reason: 'Needs approval',
      timeoutSeconds: 60,
      onTimeout: 'BLOCK',
    });

    const path = join(store.basePath, `${challengeId}.json`);
    writeFileSync(
      path,
      JSON.stringify({
        id: challengeId,
        requestId: 'req-timeout',
        reason: 'Needs approval',
        status: 'open',
        timeoutSeconds: 60,
        onTimeout: 'BLOCK',
        createdAt: '2020-01-01T00:00:00.000Z',
      }),
      'utf8',
    );

    const expired = store.expireOpen(new Date('2026-07-11T12:00:00.000Z'));
    expect(expired).toHaveLength(1);
    expect(expired[0]?.status).toBe('denied');
    expect(expired[0]?.actor).toBe('system:timeout');
    expect(store.listOpen()).toHaveLength(0);
  });
});
