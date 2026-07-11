import type { ChallengeRecord } from './store.js';

export type ChallengeNotifyChannel = 'stdout' | 'webhook';

export interface ChallengeNotifierOptions {
  webhookUrl?: string;
  fetchFn?: typeof fetch;
  logFn?: (message: string) => void;
}

export class ChallengeNotifier {
  private readonly webhookUrl?: string;
  private readonly fetchFn: typeof fetch;
  private readonly logFn: (message: string) => void;

  constructor(options: ChallengeNotifierOptions = {}) {
    this.webhookUrl = options.webhookUrl;
    this.fetchFn = options.fetchFn ?? fetch;
    this.logFn = options.logFn ?? ((message) => console.log(message));
  }

  async notify(
    record: ChallengeRecord,
    channel: ChallengeNotifyChannel,
  ): Promise<boolean> {
    if (channel === 'stdout') {
      this.notifyStdout(record);
      return true;
    }

    if (channel === 'webhook') {
      return this.notifyWebhook(record);
    }

    return false;
  }

  notifyStdout(record: ChallengeRecord): void {
    const summary = `[LexShield] CHALLENGE id=${record.id} request=${record.requestId} reason="${record.reason}" timeout=${record.timeoutSeconds}s`;
    this.logFn(summary);
  }

  async notifyWebhook(record: ChallengeRecord): Promise<boolean> {
    if (!this.webhookUrl) {
      return false;
    }

    try {
      const response = await this.fetchFn(this.webhookUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'lexshield.challenge.created',
          challenge: record,
        }),
      });
      return response.ok;
    } catch {
      return false;
    }
  }
}
