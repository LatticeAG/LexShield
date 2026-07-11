import type { Caller, CallContext, Verdict } from './types.js';

export interface LocalApiClientOptions {
  baseUrl?: string;
  shieldId?: string;
  token?: string | null;
  tokenEnv?: string;
  fetchImpl?: typeof fetch;
}

export interface EvaluateApiInput {
  tool: string;
  arguments?: Record<string, unknown>;
  caller?: Caller;
  context?: CallContext;
  requestId?: string;
}

export class LocalApiClient {
  readonly baseUrl: string;
  readonly shieldId: string;
  private readonly token?: string | null;
  private readonly tokenEnv: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: LocalApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? 'http://127.0.0.1:8787';
    this.shieldId = options.shieldId ?? 'local';
    this.tokenEnv = options.tokenEnv ?? 'LEXSHIELD_LOCAL_TOKEN';
    this.fetchImpl = options.fetchImpl ?? fetch;

    if (options.token !== undefined) {
      this.token = options.token;
    }
  }

  private resolvedToken(): string | null {
    if (this.token !== undefined) {
      return this.token;
    }
    return process.env[this.tokenEnv] ?? null;
  }

  private headers(): Record<string, string> {
    const headers: Record<string, string> = {
      'content-type': 'application/json',
    };

    const token = this.resolvedToken();
    if (token) {
      headers.authorization = `Bearer ${token}`;
    }

    return headers;
  }

  async evaluate(input: EvaluateApiInput): Promise<Verdict> {
    const requestId = input.requestId ?? crypto.randomUUID();
    const body = {
      id: requestId,
      shieldId: this.shieldId,
      timestamp: new Date().toISOString(),
      caller: input.caller ?? { id: 'anonymous', type: 'agent' },
      tool: { name: input.tool },
      arguments: input.arguments ?? {},
      context: input.context ?? {},
    };

    const response = await this.fetchImpl(
      `${this.baseUrl}/v1/shields/${encodeURIComponent(this.shieldId)}/evaluate`,
      {
        method: 'POST',
        headers: this.headers(),
        body: JSON.stringify(body),
      },
    );

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`Local API evaluate failed (${response.status}): ${detail}`);
    }

    return (await response.json()) as Verdict;
  }
}
