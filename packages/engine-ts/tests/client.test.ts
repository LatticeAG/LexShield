import { describe, expect, it } from 'vitest';

import { LocalApiClient } from '../src/client.js';

describe('LocalApiClient', () => {
  it('calls the local evaluate endpoint', async () => {
    const fetchImpl = async (url: string, init?: RequestInit) => {
      expect(url).toBe('http://127.0.0.1:8787/v1/shields/local/evaluate');
      expect(init?.method).toBe('POST');

      const body = JSON.parse(String(init?.body));
      expect(body.tool.name).toBe('health_check');

      return new Response(
        JSON.stringify({
          requestId: body.id,
          decision: 'ALLOW',
          matchedRuleId: 'allow-health',
          reason: 'Health checks are always allowed',
          classifications: [],
          durationMs: 1,
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      );
    };

    const client = new LocalApiClient({ fetchImpl });
    const verdict = await client.evaluate({ tool: 'health_check' });

    expect(verdict.decision).toBe('ALLOW');
    expect(verdict.matchedRuleId).toBe('allow-health');
  });

  it('sends bearer token when configured', async () => {
    const fetchImpl = async (_url: string, init?: RequestInit) => {
      const headers = init?.headers as Record<string, string>;
      expect(headers.authorization).toBe('Bearer test-token');

      return new Response(
        JSON.stringify({
          requestId: 'req-1',
          decision: 'BLOCK',
          reason: 'blocked',
          classifications: [],
          durationMs: 1,
        }),
        { status: 200 },
      );
    };

    const client = new LocalApiClient({ token: 'test-token', fetchImpl });
    const verdict = await client.evaluate({ tool: 'send_email' });
    expect(verdict.decision).toBe('BLOCK');
  });
});
