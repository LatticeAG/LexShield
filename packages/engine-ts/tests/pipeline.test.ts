import { describe, expect, it, beforeEach } from 'vitest';

import { LLMClassifier } from '../src/classifiers/llm.js';
import {
  CACHE_TTL_MS,
  ClassifierPipeline,
  UNKNOWN_INTENT,
  clearClassificationCache,
  mergeClassifications,
} from '../src/classifiers/pipeline.js';
import { getIntentSeverity } from '../src/taxonomy.js';
import type { Classification, ToolCallRequest } from '../src/types.js';

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

function request(tool: string, args: Record<string, unknown> = {}): ToolCallRequest {
  return {
    id: 'req-1',
    shieldId: 'local',
    timestamp: '2026-07-11T12:00:00.000Z',
    caller: { id: 'agent-1', type: 'agent' },
    tool: { name: tool },
    arguments: args,
    context: {},
  };
}

function classification(
  intent: string,
  confidence: number,
  classifier: string,
  alternatives: Classification['alternatives'] = [],
): Classification {
  return {
    intent,
    confidence,
    alternatives,
    classifier,
  };
}

describe('mergeClassifications', () => {
  it('prefers higher severity intent as primary', () => {
    const merged = mergeClassifications([
      classification('comms.send.email', 0.95, 'deterministic:v1'),
      classification('security.secret_exposure', 0.6, 'llm:openai:gpt-4o-mini'),
    ]);

    expect(merged[0]?.intent).toBe('security.secret_exposure');
    expect(merged).toHaveLength(2);
  });

  it('breaks severity ties by confidence', () => {
    const merged = mergeClassifications([
      classification('comms.send.email', 0.7, 'deterministic:v1'),
      classification('code.write.repo', 0.9, 'llm:openai:gpt-4o-mini'),
    ]);

    expect(merged[0]?.intent).toBe('code.write.repo');
  });

  it('breaks confidence ties by deterministic classifier preference', () => {
    const merged = mergeClassifications([
      classification('comms.send.email', 0.8, 'llm:openai:gpt-4o-mini'),
      classification('code.write.repo', 0.8, 'deterministic:v1'),
    ]);

    expect(merged[0]?.intent).toBe('code.write.repo');
  });
});

describe('ClassifierPipeline', () => {
  beforeEach(() => {
    clearClassificationCache();
  });

  it('classifies tool_map intents', async () => {
    const pipeline = new ClassifierPipeline({
      deterministicRules,
      llmEnabled: false,
    });

    const result = await pipeline.classify(request('health_check'));
    expect(result[0]?.intent).toBe('network.request.health');
    expect(result[0]?.confidence).toBe(0.7);
  });

  it('classifies pattern intents with high confidence', async () => {
    const pipeline = new ClassifierPipeline({
      deterministicRules,
      llmEnabled: false,
    });

    const result = await pipeline.classify(
      request('send_email', { body: 'AKIAIOSFODNN7EXAMPLE' }),
    );

    expect(result[0]?.intent).toBe('security.secret_exposure');
    expect(result[0]?.confidence).toBe(0.98);
  });

  it('falls back to unknown.unclassified with confidence 0.5', async () => {
    const pipeline = new ClassifierPipeline({
      deterministicRules,
      llmEnabled: false,
    });

    const result = await pipeline.classify(request('totally_unknown_tool'));
    expect(result[0]?.intent).toBe(UNKNOWN_INTENT);
    expect(result[0]?.confidence).toBe(0.5);
    expect(result[0]?.reasoning).toContain('No deterministic or LLM classification');
  });

  it('skips LLM when deterministic confidence is at least 0.9', async () => {
    const llm = new LLMClassifier({
      apiKey: 'test-key',
      classifyFn: async () => {
        throw new Error('LLM should not be called');
      },
    });

    const pipeline = new ClassifierPipeline({
      deterministicRules,
      llm,
    });

    const result = await pipeline.classify(
      request('send_email', { body: 'AKIAIOSFODNN7EXAMPLE' }),
    );

    expect(result).toHaveLength(1);
    expect(result[0]?.intent).toBe('security.secret_exposure');
  });

  it('appends LLM classification when deterministic confidence is below threshold', async () => {
    const llm = new LLMClassifier({
      classifyFn: async () =>
        classification('data.exfiltrate', 0.8, 'llm:openai:gpt-4o-mini'),
    });

    const pipeline = new ClassifierPipeline({
      deterministicRules,
      llm,
    });

    const result = await pipeline.classify(request('send_email'));
    expect(result[0]?.intent).toBe('data.exfiltrate');
    expect(result.some((item) => item.intent === 'comms.send.email')).toBe(true);
  });

  it('returns consistent results for repeated cacheable requests', async () => {
    const pipeline = new ClassifierPipeline({
      deterministicRules,
      llmEnabled: false,
    });

    const req = request('health_check');
    const first = await pipeline.classify(req);
    const second = await pipeline.classify(req);

    expect(first).toEqual(second);
  });

  it('does not cache when conversation context is present', async () => {
    const pipeline = new ClassifierPipeline({
      deterministicRules,
      llmEnabled: false,
    });

    const contextual = {
      ...request('health_check'),
      context: {
        messages: [{ role: 'user', content: 'check health' }],
      },
    };

    const first = await pipeline.classify(contextual);
    const second = await pipeline.classify(contextual);

    expect(first[0]?.intent).toBe(second[0]?.intent);
    expect(CACHE_TTL_MS).toBeGreaterThan(0);
  });
});

describe('taxonomy severity', () => {
  it('assigns expected severities for built-in intents', () => {
    expect(getIntentSeverity('network.request.health')).toBe(5);
    expect(getIntentSeverity('security.secret_exposure')).toBe(98);
    expect(getIntentSeverity('unknown.unclassified')).toBe(50);
    expect(getIntentSeverity('custom.my_intent')).toBe(50);
  });
});
