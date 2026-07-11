import { describe, expect, it, vi } from 'vitest';

import { LLMClassifier } from '../src/classifiers/llm.js';
import { BUILTIN_INTENTS } from '../src/taxonomy.js';
import type { ToolCallRequest } from '../src/types.js';

function request(argumentsPayload: Record<string, unknown> = { body: 'hello' }): ToolCallRequest {
  return {
    id: '01JTEST',
    shieldId: 'local',
    timestamp: '2026-07-11T12:00:00.000Z',
    caller: { id: 'agent-1', type: 'agent' },
    tool: { name: 'send_email' },
    arguments: argumentsPayload,
    context: {},
  };
}

function chatResponse(content: Record<string, unknown>) {
  return {
    choices: [{ message: { content: JSON.stringify(content) } }],
  };
}

describe('LLMClassifier', () => {
  it('returns null without API key when optional', async () => {
    const classifier = new LLMClassifier({ optional: true, apiKey: null });
    const result = await classifier.classify(request());
    expect(result).toBeNull();
  });

  it('throws without API key when not optional', async () => {
    const classifier = new LLMClassifier({ optional: false, apiKey: null });
    await expect(classifier.classify(request())).rejects.toThrow('OPENAI_API_KEY');
  });

  it('classifies successfully via OpenAI-compatible API', async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () =>
        chatResponse({
          intent: 'comms.send.email',
          confidence: 0.82,
          alternatives: [{ intent: 'comms.send.external', confidence: 0.2 }],
          reasoning: 'Email tool with recipient arguments',
        }),
    });

    const classifier = new LLMClassifier({
      apiKey: 'test-key',
      baseUrl: 'https://api.example.com/v1',
      fetchFn,
    });

    const result = await classifier.classify(request());

    expect(result).toEqual({
      intent: 'comms.send.email',
      confidence: 0.82,
      alternatives: [{ intent: 'comms.send.external', confidence: 0.2 }],
      classifier: 'llm:openai:gpt-4o-mini',
      reasoning: 'Email tool with recipient arguments',
    });

    expect(fetchFn).toHaveBeenCalledOnce();
    const call = fetchFn.mock.calls[0]!;
    expect(call[0]).toBe('https://api.example.com/v1/chat/completions');
    const body = JSON.parse((call[1] as RequestInit).body as string) as Record<string, unknown>;
    expect(body.model).toBe('gpt-4o-mini');
    expect(body.response_format).toEqual({ type: 'json_object' });

    const systemPrompt = (body.messages as Array<Record<string, string>>)[0]!.content;
    for (const intent of BUILTIN_INTENTS) {
      expect(systemPrompt).toContain(intent);
    }
  });

  it('redacts secrets and emails in user prompt', async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () =>
        chatResponse({
          intent: 'security.secret_exposure',
          confidence: 0.95,
          alternatives: [],
          reasoning: 'AWS key detected',
        }),
    });

    const classifier = new LLMClassifier({
      apiKey: 'test-key',
      baseUrl: 'https://api.example.com/v1',
      fetchFn,
    });

    await classifier.classify(
      request({ body: 'key=AKIAIOSFODNN7EXAMPLE', to: 'user@example.com' }),
    );

    const body = JSON.parse((fetchFn.mock.calls[0]![1] as RequestInit).body as string) as Record<
      string,
      unknown
    >;
    const userPrompt = (body.messages as Array<Record<string, string>>)[1]!.content;
    expect(userPrompt).not.toContain('AKIAIOSFODNN7EXAMPLE');
    expect(userPrompt).toContain('[REDACTED_AWS_KEY]');
    expect(userPrompt).not.toContain('user@example.com');
    expect(userPrompt).toContain('[REDACTED_EMAIL]');
  });

  it('returns null on HTTP error', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ ok: false, status: 500 });
    const classifier = new LLMClassifier({
      apiKey: 'test-key',
      fetchFn,
    });

    const result = await classifier.classify(request());
    expect(result).toBeNull();
  });

  it('returns null on invalid JSON content', async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ choices: [{ message: { content: 'not-json' } }] }),
    });

    const classifier = new LLMClassifier({
      apiKey: 'test-key',
      fetchFn,
    });

    const result = await classifier.classify(request());
    expect(result).toBeNull();
  });

  it('normalizes provider-prefixed model names', () => {
    const classifier = new LLMClassifier({ model: 'openai:gpt-4o-mini' });
    expect(classifier.model).toBe('gpt-4o-mini');
  });
});
