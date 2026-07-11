import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';

import type { VerdictType } from '../types.js';

export interface ChallengeRecord {
  id: string;
  requestId: string;
  reason: string;
  status: 'open' | 'approved' | 'denied';
  timeoutSeconds: number;
  onTimeout: VerdictType;
  createdAt: string;
  resolvedAt?: string;
  actor?: string;
}

export class ChallengeStore {
  readonly basePath: string;

  constructor(basePath = '.lexshield/challenges') {
    this.basePath = basePath;
    if (!existsSync(this.basePath)) {
      mkdirSync(this.basePath, { recursive: true });
    }
  }

  create(options: {
    requestId: string;
    reason: string;
    timeoutSeconds?: number;
    onTimeout?: VerdictType;
  }): string {
    const challengeId = randomUUID();
    const record: ChallengeRecord = {
      id: challengeId,
      requestId: options.requestId,
      reason: options.reason,
      status: 'open',
      timeoutSeconds: options.timeoutSeconds ?? 3600,
      onTimeout: options.onTimeout ?? 'BLOCK',
      createdAt: new Date().toISOString(),
    };

    const path = join(this.basePath, `${challengeId}.json`);
    writeFileSync(path, JSON.stringify(record, null, 2), 'utf8');
    return challengeId;
  }

  listOpen(): ChallengeRecord[] {
    const openChallenges: ChallengeRecord[] = [];

    if (!existsSync(this.basePath)) {
      return openChallenges;
    }

    for (const fileName of readdirSync(this.basePath).sort()) {
      if (!fileName.endsWith('.json')) {
        continue;
      }

      const path = join(this.basePath, fileName);
      const record = JSON.parse(readFileSync(path, 'utf8')) as ChallengeRecord;
      if (record.status === 'open') {
        openChallenges.push(record);
      }
    }

    return openChallenges;
  }

  get(challengeId: string): ChallengeRecord | null {
    const path = join(this.basePath, `${challengeId}.json`);
    if (!existsSync(path)) {
      return null;
    }

    return JSON.parse(readFileSync(path, 'utf8')) as ChallengeRecord;
  }

  /**
   * Resolve open challenges that have exceeded their timeout.
   * Applies onTimeout: ALLOW -> approved, BLOCK -> denied.
   */
  expireOpen(now: Date = new Date()): ChallengeRecord[] {
    const expired: ChallengeRecord[] = [];

    for (const record of this.listOpen()) {
      const deadline =
        new Date(record.createdAt).getTime() + record.timeoutSeconds * 1000;
      if (now.getTime() < deadline) {
        continue;
      }

      const updated: ChallengeRecord = {
        ...record,
        status: record.onTimeout === 'ALLOW' ? 'approved' : 'denied',
        resolvedAt: now.toISOString(),
        actor: 'system:timeout',
      };

      const path = join(this.basePath, `${record.id}.json`);
      writeFileSync(path, JSON.stringify(updated, null, 2), 'utf8');
      expired.push(updated);
    }

    return expired;
  }

  resolve(
    challengeId: string,
    options: {
      decision: 'approve' | 'deny';
      actor: string;
    },
  ): ChallengeRecord | null {
    const path = join(this.basePath, `${challengeId}.json`);
    if (!existsSync(path)) {
      return null;
    }

    const record = JSON.parse(readFileSync(path, 'utf8')) as ChallengeRecord;
    record.status = options.decision === 'approve' ? 'approved' : 'denied';
    record.resolvedAt = new Date().toISOString();
    record.actor = options.actor;
    writeFileSync(path, JSON.stringify(record, null, 2), 'utf8');
    return record;
  }
}
