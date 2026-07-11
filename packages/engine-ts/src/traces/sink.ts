import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

import type { OutcomeType, Trace } from '../types.js';

export class NDJSONTraceSink {
  readonly path: string;

  constructor(path: string) {
    this.path = path;
    const parent = dirname(path);
    if (!existsSync(parent)) {
      mkdirSync(parent, { recursive: true });
    }
  }

  write(trace: Trace): void {
    const line = `${JSON.stringify(trace)}\n`;
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

  updateOutcome(requestId: string, outcome: OutcomeType): boolean {
    if (!existsSync(this.path)) {
      return false;
    }

    const lines = readFileSync(this.path, 'utf8').split('\n');
    let updated = false;

    const rewritten: string[] = [];
    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }

      const record = JSON.parse(line) as Trace;
      const traceRequestId = record.id ?? record.request?.id;
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

    return updated;
  }
}
