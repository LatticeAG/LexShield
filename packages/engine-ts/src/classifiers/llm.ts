import type { Classification, ToolCallRequest } from '../types.js';
import { redactArguments } from '../redaction.js';
import { BUILTIN_INTENTS } from '../taxonomy.js';

const SYSTEM_PROMPT_TEMPLATE = `You classify agent tool calls into intents for a policy firewall.

Allowed intents (use exactly one as primary):
{intents}

Safety rules:
- Prefer unknown.unclassified over guessing a dangerous intent as benign.
- Base classification on tool name, arguments, and caller context.
- Return JSON only with keys: intent, confidence, alternatives, reasoning.
- confidence must be between 0 and 1.
- alternatives is a list of {intent, confidence} objects.`;

export interface LLMClassifierOptions {
  model?: string;
  apiKeyEnv?: string;
  baseUrlEnv?: string;
  timeoutMs?: number;
  optional?: boolean;
  redact?: boolean;
  /** Injectable classify implementation for tests and mocks. */
  classifyFn?: (request: ToolCallRequest) => Promise<Classification | null>;
  /** Injectable API key resolver for tests. */
  apiKey?: string | null;
  /** Injectable base URL resolver for tests. */
  baseUrl?: string;
  /** Injectable fetch for tests. */
  fetchFn?: typeof fetch;
}

function normalizeModel(model: string): string {
  if (model.includes(':')) {
    return model.split(':', 1)[1]!;
  }
  return model;
}

export class LLMClassifier {
  readonly model: string;
  readonly apiKeyEnv: string;
  readonly baseUrlEnv: string;
  readonly timeoutMs: number;
  readonly optional: boolean;
  readonly redact: boolean;
  private readonly classifyFn?: (request: ToolCallRequest) => Promise<Classification | null>;
  private readonly injectedApiKey?: string | null;
  private readonly injectedBaseUrl?: string;
  private readonly fetchFn: typeof fetch;

  constructor(options: LLMClassifierOptions = {}) {
    this.model = normalizeModel(options.model ?? 'gpt-4o-mini');
    this.apiKeyEnv = options.apiKeyEnv ?? 'OPENAI_API_KEY';
    this.baseUrlEnv = options.baseUrlEnv ?? 'OPENAI_BASE_URL';
    this.timeoutMs = options.timeoutMs ?? 2000;
    this.optional = options.optional ?? true;
    this.redact = options.redact ?? true;
    this.classifyFn = options.classifyFn;
    this.injectedApiKey = options.apiKey;
    this.injectedBaseUrl = options.baseUrl;
    this.fetchFn = options.fetchFn ?? fetch;
  }

  get apiKey(): string | null {
    if (this.injectedApiKey !== undefined) {
      return this.injectedApiKey;
    }
    return process.env[this.apiKeyEnv] ?? null;
  }

  get baseUrl(): string {
    const url =
      this.injectedBaseUrl !== undefined
        ? this.injectedBaseUrl
        : (process.env[this.baseUrlEnv] ?? 'https://api.openai.com/v1');
    return url.replace(/\/$/, '');
  }

  isAvailable(): boolean {
    return Boolean(this.apiKey) || Boolean(this.classifyFn);
  }

  private systemPrompt(): string {
    const intents = BUILTIN_INTENTS.map((intent) => `- ${intent}`).join('\n');
    return SYSTEM_PROMPT_TEMPLATE.replace('{intents}', intents);
  }

  private buildUserPrompt(request: ToolCallRequest): string {
    const argumentsPayload = this.redact
      ? redactArguments(request.arguments, { emails: 'redact' })
      : request.arguments;

    const payload: Record<string, unknown> = {
      tool: request.tool.name,
      arguments: argumentsPayload,
      caller: {
        id: request.caller.id,
        type: request.caller.type,
      },
    };

    if (request.caller.roles?.length) {
      (payload.caller as Record<string, unknown>).roles = request.caller.roles;
    }
    if (request.context.environment) {
      payload.environment = request.context.environment;
    }
    if (request.context.tags) {
      payload.tags = request.context.tags;
    }

    return JSON.stringify(payload, Object.keys(payload).sort());
  }

  private parseResponse(content: string): Classification | null {
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(content) as Record<string, unknown>;
    } catch {
      return null;
    }

    const intent = data.intent;
    const confidence = data.confidence;
    if (typeof intent !== 'string' || typeof confidence !== 'number') {
      return null;
    }

    const alternatives: Classification['alternatives'] = [];
    const rawAlternatives = data.alternatives;
    if (Array.isArray(rawAlternatives)) {
      for (const item of rawAlternatives) {
        if (!item || typeof item !== 'object') {
          continue;
        }
        const altIntent = (item as Record<string, unknown>).intent;
        const altConfidence = (item as Record<string, unknown>).confidence;
        if (typeof altIntent === 'string' && typeof altConfidence === 'number') {
          alternatives.push({ intent: altIntent, confidence: altConfidence });
        }
      }
    }

    const reasoning = data.reasoning;
    return {
      intent,
      confidence,
      alternatives,
      classifier: `llm:openai:${this.model}`,
      reasoning: typeof reasoning === 'string' ? reasoning : undefined,
    };
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

    const body = {
      model: this.model,
      response_format: { type: 'json_object' },
      messages: [
        { role: 'system', content: this.systemPrompt() },
        { role: 'user', content: this.buildUserPrompt(request) },
      ],
    };

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await this.fetchFn(`${this.baseUrl}/chat/completions`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        return null;
      }

      const payload = (await response.json()) as Record<string, unknown>;
      const choices = payload.choices;
      if (!Array.isArray(choices) || choices.length === 0) {
        return null;
      }

      const message = (choices[0] as Record<string, unknown>)?.message;
      const content = (message as Record<string, unknown> | undefined)?.content;
      if (typeof content !== 'string') {
        return null;
      }

      return this.parseResponse(content);
    } catch {
      return null;
    } finally {
      clearTimeout(timeout);
    }
  }
}
