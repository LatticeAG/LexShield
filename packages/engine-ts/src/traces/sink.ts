import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

import { redactArguments } from '../redaction.js';
import type {
  Classification,
  OutcomeType,
  ToolCallRequest,
  Trace,
  Verdict,
  VerdictType,
} from '../types.js';

export interface TraceSink {
  write(payload: Record<string, unknown>): void;
  updateOutcome(requestId: string, outcome: OutcomeType | string): void;
}

function outcomeForVerdict(decision: VerdictType): OutcomeType {
  const mapping: Record<VerdictType, OutcomeType> = {
    ALLOW: 'EXECUTED',
    BLOCK: 'BLOCKED',
    CHALLENGE: 'CHALLENGED',
    DEFER: 'DEFERRED',
  };
  return mapping[decision];
}

export function buildTracePayload(options: {
  traceId: string;
  shieldId: string;
  timestamp: string;
  request: ToolCallRequest;
  classifications: Classification[];
  verdict: Verdict;
  outcome?: OutcomeType;
  redactEmails?: 'hash' | 'redact' | 'off';
}): Record<string, unknown> {
  const redactedArgs = redactArguments(options.request.arguments, {
    emails: options.redactEmails ?? 'hash',
  });

  const verdictPayload: Record<string, unknown> = {
    decision: options.verdict.decision,
    reason: options.verdict.reason,
    durationMs: options.verdict.durationMs,
  };

  if (options.verdict.matchedRuleId !== undefined) {
    verdictPayload.matchedRuleId = options.verdict.matchedRuleId;
  }
  if (options.verdict.policyVersion !== undefined) {
    verdictPayload.policyVersion = options.verdict.policyVersion;
  }
  if (options.verdict.challengeId !== undefined) {
    verdictPayload.challengeId = options.verdict.challengeId;
  }

  return {
    id: options.traceId,
    ts: options.timestamp,
    shieldId: options.shieldId,
    request: {
      id: options.request.id,
      caller: options.request.caller,
      tool: options.request.tool,
      arguments_redacted: redactedArgs,
      context: options.request.context,
    },
    classifications: options.classifications,
    verdict: verdictPayload,
    outcome: options.outcome ?? outcomeForVerdict(options.verdict.decision),
  };
}

export class NDJSONTraceSink implements TraceSink {
  readonly path: string;

  constructor(path: string) {
    this.path = path;
    const parent = dirname(path);
    if (!existsSync(parent)) {
      mkdirSync(parent, { recursive: true });
    }
  }

  write(payload: Record<string, unknown> | Trace): void {
    const line = `${JSON.stringify(payload)}\n`;
    appendFileSync(this.path, line, 'utf8');
  }

  readAll(options: { limit?: number; offset?: number } = {}): Array<Record<string, unknown>> {
    const limit = options.limit ?? 100;
    const offset = options.offset ?? 0;

    if (!existsSync(this.path)) {
      return [];
    }

    const lines = readFileSync(this.path, 'utf8').split('\n').filter((line) => line.trim());
    const selected = lines.slice(offset, offset + limit);
    return selected.map((line) => JSON.parse(line) as Record<string, unknown>);
  }

  updateOutcome(requestId: string, outcome: OutcomeType | string): void {
    if (!existsSync(this.path)) {
      return;
    }

    const lines = readFileSync(this.path, 'utf8').split('\n');
    let updated = false;

    const rewritten: string[] = [];
    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }

      const record = JSON.parse(line) as Record<string, unknown>;
      const traceRequestId =
        (record.id as string | undefined) ??
        ((record.request as Record<string, unknown> | undefined)?.id as string | undefined);
      if (traceRequestId !== requestId) {
        rewritten.push(line);
        continue;
      }

      updated = true;
      rewritten.push(
        JSON.stringify({
          ...record,
          outcome,
          outcomeAt: new Date().toISOString(),
        }),
      );
    }

    if (updated) {
      writeFileSync(this.path, `${rewritten.join('\n')}\n`, 'utf8');
    }
  }
}

export class StdoutTraceSink implements TraceSink {
  private readonly logFn: (message: string) => void;

  constructor(options: { logFn?: (message: string) => void } = {}) {
    this.logFn = options.logFn ?? ((message) => console.log(message));
  }

  write(payload: Record<string, unknown>): void {
    const verdict = (payload.verdict as Record<string, unknown> | undefined) ?? {};
    const request = (payload.request as Record<string, unknown> | undefined) ?? {};
    const tool = ((request.tool as Record<string, unknown> | undefined)?.name as string) ?? '?';
    const decision = (verdict.decision as string) ?? '?';
    const ruleId = (verdict.matchedRuleId as string | undefined) ?? '-';

    const classifications = payload.classifications as Array<Record<string, unknown>> | undefined;
    const intent = classifications?.[0]?.intent as string | undefined;

    let summary = `[LexShield] ${decision} ${tool}`;
    if (intent) {
      summary += ` ${intent}`;
    }
    summary += ` rule=${ruleId}`;
    this.logFn(summary);
  }

  updateOutcome(_requestId: string, _outcome: OutcomeType | string): void {
    // stdout sink does not persist outcomes
  }
}

export interface HttpTraceSinkOptions {
  url: string;
  headers?: Record<string, string>;
  timeoutMs?: number;
  fetchFn?: typeof fetch;
}

export class HttpTraceSink implements TraceSink {
  private readonly url: string;
  private readonly headers: Record<string, string>;
  private readonly timeoutMs: number;
  private readonly fetchFn: typeof fetch;

  constructor(options: HttpTraceSinkOptions) {
    this.url = options.url;
    this.headers = options.headers ?? {};
    this.timeoutMs = options.timeoutMs ?? 5000;
    this.fetchFn = options.fetchFn ?? fetch;
  }

  write(payload: Record<string, unknown>): void {
    void this.post(payload);
  }

  updateOutcome(_requestId: string, _outcome: OutcomeType | string): void {
    // HTTP sink does not patch prior events
  }

  private async post(payload: Record<string, unknown>): Promise<void> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      await this.fetchFn(this.url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...this.headers,
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
    } catch {
      // best-effort sink
    } finally {
      clearTimeout(timeout);
    }
  }
}

export interface OtlpTraceSinkOptions {
  endpoint: string;
  serviceName?: string;
  headers?: Record<string, string>;
  timeoutMs?: number;
  fetchFn?: typeof fetch;
}

export class OtlpTraceSink implements TraceSink {
  private readonly endpoint: string;
  private readonly serviceName: string;
  private readonly headers: Record<string, string>;
  private readonly timeoutMs: number;
  private readonly fetchFn: typeof fetch;

  constructor(options: OtlpTraceSinkOptions) {
    this.endpoint = options.endpoint.replace(/\/$/, '');
    this.serviceName = options.serviceName ?? 'lexshield';
    this.headers = options.headers ?? {};
    this.timeoutMs = options.timeoutMs ?? 5000;
    this.fetchFn = options.fetchFn ?? fetch;
  }

  write(payload: Record<string, unknown>): void {
    void this.exportSpan(payload);
  }

  updateOutcome(_requestId: string, _outcome: OutcomeType | string): void {
    // OTLP sink does not patch prior events
  }

  private async exportSpan(payload: Record<string, unknown>): Promise<void> {
    const verdict = (payload.verdict as Record<string, unknown> | undefined) ?? {};
    const request = (payload.request as Record<string, unknown> | undefined) ?? {};
    const tool = ((request.tool as Record<string, unknown> | undefined)?.name as string) ?? 'unknown';
    const classifications = payload.classifications as Array<Record<string, unknown>> | undefined;
    const intent = (classifications?.[0]?.intent as string | undefined) ?? 'unknown.unclassified';
    const traceId = (payload.id as string | undefined) ?? 'unknown';
    const durationMs = (verdict.durationMs as number | undefined) ?? 0;
    const nowNs = BigInt(Date.now()) * 1_000_000n;

    const otlpPayload = {
      resourceSpans: [
        {
          resource: {
            attributes: [
              { key: 'service.name', value: { stringValue: this.serviceName } },
            ],
          },
          scopeSpans: [
            {
              spans: [
                {
                  traceId: traceId.padStart(32, '0').slice(0, 32),
                  spanId: traceId.replace(/-/g, '').slice(0, 16).padStart(16, '0'),
                  name: 'lexshield.evaluate',
                  kind: 1,
                  startTimeUnixNano: String(nowNs - BigInt(durationMs) * 1_000_000n),
                  endTimeUnixNano: String(nowNs),
                  attributes: [
                    { key: 'lexshield.tool', value: { stringValue: tool } },
                    { key: 'lexshield.intent', value: { stringValue: intent } },
                    { key: 'lexshield.verdict', value: { stringValue: String(verdict.decision ?? '') } },
                    {
                      key: 'lexshield.rule_id',
                      value: { stringValue: String(verdict.matchedRuleId ?? '') },
                    },
                  ],
                },
              ],
            },
          ],
        },
      ],
    };

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      await this.fetchFn(`${this.endpoint}/v1/traces`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...this.headers,
        },
        body: JSON.stringify(otlpPayload),
        signal: controller.signal,
      });
    } catch {
      // best-effort sink
    } finally {
      clearTimeout(timeout);
    }
  }
}

export class CompositeTraceSink implements TraceSink {
  private readonly sinks: TraceSink[];

  constructor(sinks: TraceSink[]) {
    this.sinks = sinks;
  }

  write(payload: Record<string, unknown>): void {
    for (const sink of this.sinks) {
      sink.write(payload);
    }
  }

  updateOutcome(requestId: string, outcome: OutcomeType | string): void {
    for (const sink of this.sinks) {
      sink.updateOutcome(requestId, outcome);
    }
  }
}
