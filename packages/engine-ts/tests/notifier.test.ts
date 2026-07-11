import { describe, expect, it, vi } from 'vitest';

import { ChallengeNotifier } from '../src/challenges/notifier.js';
import type { ChallengeRecord } from '../src/challenges/store.js';

const record: ChallengeRecord = {
  id: 'challenge-1',
  requestId: 'req-1',
  reason: 'Needs approval',
  status: 'open',
  timeoutSeconds: 3600,
  onTimeout: 'BLOCK',
  createdAt: '2026-07-11T12:00:00.000Z',
};

describe('ChallengeNotifier', () => {
  it('writes challenge summary to stdout channel', async () => {
    const lines: string[] = [];
    const notifier = new ChallengeNotifier({ logFn: (message) => lines.push(message) });

    const ok = await notifier.notify(record, 'stdout');

    expect(ok).toBe(true);
    expect(lines[0]).toContain('CHALLENGE id=challenge-1 request=req-1');
  });

  it('posts challenge payload to webhook channel', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ ok: true });
    const notifier = new ChallengeNotifier({
      webhookUrl: 'https://hooks.example.com/challenge',
      fetchFn,
    });

    const ok = await notifier.notify(record, 'webhook');

    expect(ok).toBe(true);
    expect(fetchFn).toHaveBeenCalledOnce();
    expect(fetchFn.mock.calls[0]![0]).toBe('https://hooks.example.com/challenge');
    const body = JSON.parse((fetchFn.mock.calls[0]![1] as RequestInit).body as string) as Record<
      string,
      unknown
    >;
    expect(body.type).toBe('lexshield.challenge.created');
  });

  it('returns false for webhook when URL is not configured', async () => {
    const notifier = new ChallengeNotifier();
    const ok = await notifier.notify(record, 'webhook');
    expect(ok).toBe(false);
  });
});
