import type { Classification, ToolCallRequest } from '../types.js';
import { redactArguments } from '../redaction.js';

export interface LLMClassifierOptions {
  model?: string;
  apiKeyEnv?: string;
  baseUrlEnv?: string;
  timeoutMs?: number;
  optional?: boolean;
  /** Injectable classify implementation for tests and mocks. */
  classifyFn?: (request: ToolCallRequest) => Promise<Classification | null>;
  /** Injectable API key resolver for tests. */
  apiKey?: string | null;
  /** Injectable base URL resolver for tests. */
  baseUrl?: string;
}

export class LLMClassifier {
  readonly model: string;
  readonly apiKeyEnv: string;
  readonly baseUrlEnv: string;
  readonly timeoutMs: number;
  readonly optional: boolean;
  private readonly classifyFn?: (request: ToolCallRequest) => Promise<Classification | null>;
  private readonly injectedApiKey?: string | null;
  private readonly injectedBaseUrl?: string;

  constructor(options: LLMClassifierOptions = {}) {
    this.model = options.model ?? 'gpt-4o-mini';
    this.apiKeyEnv = options.apiKeyEnv ?? 'OPENAI_API_KEY';
    this.baseUrlEnv = options.baseUrlEnv ?? 'OPENAI_BASE_URL';
    this.timeoutMs = options.timeoutMs ?? 2000;
    this.optional = options.optional ?? true;
    this.classifyFn = options.classifyFn;
    this.injectedApiKey = options.apiKey;
    this.injectedBaseUrl = options.baseUrl;
  }

  get apiKey(): string | null {
    if (this.injectedApiKey !== undefined) {
      return this.injectedApiKey;
    }
    return process.env[this.apiKeyEnv] ?? null;
  }

  get baseUrl(): string {
    if (this.injectedBaseUrl !== undefined) {
      return this.injectedBaseUrl;
    }
    return process.env[this.baseUrlEnv] ?? 'https://api.openai.com/v1';
  }

  isAvailable(): boolean {
    return Boolean(this.apiKey) || Boolean(this.classifyFn);
  }

  async classify(request: ToolCallRequest): Promise<Classification | null> {
    if (this.classifyFn) {
      return this.classifyFn(request);
    }

    if (!this.isAvailable()) {
      if (this.optional) {
        return null;
      }
      throw new Error(`Missing API key env var: ${this.apiKeyEnv}`);
    }

    const redactedArgs = redactArguments(request.arguments, { emails: 'redact' });
    void redactedArgs;

    // Stub: no live LLM call in OSS v0.1 scaffold; reserved for OpenAI-compatible client.
    return {
      intent: 'unknown.unclassified',
      confidence: 0.5,
      alternatives: [{ intent: 'unknown.unclassified', confidence: 0.5 }],
      classifier: `llm:openai:${this.model}`,
      reasoning: 'LLM classifier stub',
    };
  }
}
