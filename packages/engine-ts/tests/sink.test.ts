import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  CompositeTraceSink,
  HttpTraceSink,
  NDJSONTraceSink,
  OtlpTraceSink,
  StdoutTraceSink,
  buildTracePayload,
} from '../src/traces/sink.js';
import type { ToolCallRequest, Verdict } from '../src/types.js';

const tempDirs: string[] = [];

afterEach(() => {
  for (const dir of tempDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

function makeTempDir(): string {
  const dir = mkdtempSync(join(tmpdir(), 'lexshield-sink-'));
  tempDirs.push(dir);
  return dir;
}

const request: ToolCallRequest = {
  id: 'trace-1',
  shieldId: 'local',
  timestamp: '2026-07-11T12:00:00.000Z',
  caller: { id: 'agent-1', type: 'agent' },
  tool: { name: 'send_email' },
  arguments: { body: 'hello' },
  context: { environment: 'production' },
};

const verdict: Verdict = {
  requestId: 'trace-1',
  decision: 'ALLOW',
  matchedRuleId: 'allow-health',
  reason: 'Allowed',
  classifications: [],
  durationMs: 3,
};

describe('buildTracePayload', () => {
  it('builds Appendix C trace shape', () => {
    const payload = buildTracePayload({
      traceId: 'trace-1',
      shieldId: 'local',
      timestamp: request.timestamp,
      request,
      classifications: [
        {
          intent: 'comms.send.email',
          confidence: 0.7,
          alternatives: [],
          classifier: 'deterministic:v1',
        },
      ],
      verdict,
    });

    expect(payload.id).toBe('trace-1');
    expect(payload.shieldId).toBe('local');
    expect((payload.request as Record<string, unknown>).arguments_redacted).toEqual({
      body: 'hello',
    });
    expect(payload.outcome).toBe('EXECUTED');
  });
});

describe('NDJSONTraceSink', () => {
  it('writes and updates outcomes', () => {
    const path = join(makeTempDir(), 'traces.ndjson');
    const sink = new NDJSONTraceSink(path);
    const payload = buildTracePayload({
      traceId: 'trace-1',
      shieldId: 'local',
      timestamp: request.timestamp,
      request,
      classifications: [],
      verdict,
    });

    sink.write(payload);
    sink.updateOutcome('trace-1', 'EXECUTED');

    const lines = readFileSync(path, 'utf8').trim().split('\n');
    const record = JSON.parse(lines[0]!) as Record<string, unknown>;
    expect(record.outcome).toBe('EXECUTED');
    expect(record.outcomeAt).toBeTruthy();
  });
});

describe('StdoutTraceSink', () => {
  it('prints one-line summary', () => {
    const lines: string[] = [];
    const sink = new StdoutTraceSink({ logFn: (message) => lines.push(message) });

    sink.write(
      buildTracePayload({
        traceId: 'trace-1',
        shieldId: 'local',
        timestamp: request.timestamp,
        request,
        classifications: [
          {
            intent: 'comms.send.email',
            confidence: 0.7,
            alternatives: [],
            classifier: 'deterministic:v1',
          },
        ],
        verdict,
      }),
    );

    expect(lines[0]).toContain('[LexShield] ALLOW send_email comms.send.email rule=allow-health');
  });
});

describe('HttpTraceSink', () => {
  it('posts trace payload to configured URL', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ ok: true });
    const sink = new HttpTraceSink({
      url: 'https://collector.example.com/traces',
      fetchFn,
    });

    const payload = { id: 'trace-1', verdict: { decision: 'ALLOW' } };
    sink.write(payload);

    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledOnce());
    expect(fetchFn.mock.calls[0]![0]).toBe('https://collector.example.com/traces');
  });
});

describe('OtlpTraceSink', () => {
  it('exports minimal OTLP span payload', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ ok: true });
    const sink = new OtlpTraceSink({
      endpoint: 'https://otel.example.com',
      fetchFn,
    });

    sink.write(
      buildTracePayload({
        traceId: 'trace-1',
        shieldId: 'local',
        timestamp: request.timestamp,
        request,
        classifications: [
          {
            intent: 'comms.send.email',
            confidence: 0.7,
            alternatives: [],
            classifier: 'deterministic:v1',
          },
        ],
        verdict,
      }),
    );

    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledOnce());
    expect(fetchFn.mock.calls[0]![0]).toBe('https://otel.example.com/v1/traces');
    const body = JSON.parse((fetchFn.mock.calls[0]![1] as RequestInit).body as string) as Record<
      string,
      unknown
    >;
    const spans = (
      (body.resourceSpans as Array<Record<string, unknown>>)[0]!.scopeSpans as Array<
        Record<string, unknown>
      >
    )[0]!.spans as Array<Record<string, unknown>>;
    expect(spans[0]!.name).toBe('lexshield.evaluate');
  });
});

describe('CompositeTraceSink', () => {
  it('delegates write and updateOutcome to all sinks', () => {
    const path = join(makeTempDir(), 'traces.ndjson');
    const lines: string[] = [];
    const composite = new CompositeTraceSink([
      new NDJSONTraceSink(path),
      new StdoutTraceSink({ logFn: (message) => lines.push(message) }),
    ]);

    const payload = buildTracePayload({
      traceId: 'trace-1',
      shieldId: 'local',
      timestamp: request.timestamp,
      request,
      classifications: [],
      verdict,
    });

    composite.write(payload);
    composite.updateOutcome('trace-1', 'EXECUTED');

    expect(readFileSync(path, 'utf8')).toContain('"outcome":"EXECUTED"');
    expect(lines[0]).toContain('[LexShield]');
  });
});
