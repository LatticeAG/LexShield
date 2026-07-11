import { existsSync, readFileSync } from 'node:fs';
import { readFile as readFileAsync } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { AsyncLocalStorage } from 'node:async_hooks';
import { randomUUID } from 'node:crypto';
import { parse as parseYaml } from 'yaml';

import { ChallengeNotifier } from './challenges/notifier.js';
import { ChallengeStore } from './challenges/store.js';
import { ClassifierPipeline } from './classifiers/pipeline.js';
import { LLMClassifier } from './classifiers/llm.js';
import {
  LexShieldBlockedError,
  LexShieldChallengeError,
  LexShieldConfigError,
} from './errors.js';
import { evaluatePolicy } from './policy/engine.js';
import { loadPolicyFromFile, loadPolicyFromFileSync, resolvePolicyPath } from './policy/loader.js';
import {
  buildTracePayload,
  CompositeTraceSink,
  HttpTraceSink,
  NDJSONTraceSink,
  OtlpTraceSink,
  StdoutTraceSink,
  type TraceSink,
} from './traces/sink.js';
import {
  DeterministicRulesSchema,
  ShieldConfigSchema,
  ToolCallRequestSchema,
  type OutcomeType,
  type Policy,
  type ShieldConfig,
  type SinkConfig,
  type ToolCallRequest,
  type Verdict,
} from './types.js';

interface SessionContext {
  conversationId?: string;
  environment?: string;
  tags?: Record<string, string>;
}

const sessionStorage = new AsyncLocalStorage<SessionContext>();

export interface ShieldOptions {
  config: ShieldConfig;
  policy: Policy;
  policyPath: string;
  classifierPipeline?: ClassifierPipeline;
  challengeStore?: ChallengeStore;
  challengeNotifier?: ChallengeNotifier;
  traceSinks?: TraceSink[];
  /** @deprecated Use traceSinks. Kept for backward compatibility. */
  traceSink?: NDJSONTraceSink | null;
}

export interface EvaluateInput {
  tool: string;
  arguments?: Record<string, unknown>;
  caller?: ToolCallRequest['caller'];
  context?: ToolCallRequest['context'];
  id?: string;
  requestId?: string;
  timestamp?: string;
}

export interface GuardOptions {
  awaitChallenge?: boolean;
}

export class ShieldSession {
  private readonly context: SessionContext;
  private readonly parent?: SessionContext;

  constructor(options: {
    conversationId?: string;
    environment?: string;
    tags?: Record<string, string>;
  } = {}) {
    this.context = {
      conversationId: options.conversationId,
      environment: options.environment,
      tags: options.tags,
    };
    this.parent = sessionStorage.getStore();
  }

  run<T>(fn: () => T): T {
    return sessionStorage.run({ ...this.parent, ...this.context }, fn);
  }

  async runAsync<T>(fn: () => Promise<T>): Promise<T> {
    return sessionStorage.run({ ...this.parent, ...this.context }, fn);
  }
}

function createTraceSinksFromConfig(
  configPath: string,
  sinks: SinkConfig[],
): TraceSink[] {
  const baseDir = dirname(resolve(configPath));
  const traceSinks: TraceSink[] = [];

  for (const sink of sinks) {
    if (sink.type === 'file') {
      const relativePath =
        sink.path ?? (sink.options.path as string | undefined) ?? './traces.ndjson';
      traceSinks.push(new NDJSONTraceSink(resolve(baseDir, relativePath)));
      continue;
    }

    if (sink.type === 'stdout') {
      traceSinks.push(new StdoutTraceSink());
      continue;
    }

    if (sink.type === 'http') {
      const url = (sink.options.url as string | undefined) ?? sink.path;
      if (url) {
        traceSinks.push(
          new HttpTraceSink({
            url,
            headers: sink.options.headers as Record<string, string> | undefined,
            timeoutMs: sink.options.timeoutMs as number | undefined,
          }),
        );
      }
      continue;
    }

    if (sink.type === 'otlp') {
      const endpoint = (sink.options.endpoint as string | undefined) ?? sink.path;
      if (endpoint) {
        traceSinks.push(
          new OtlpTraceSink({
            endpoint,
            serviceName: sink.options.serviceName as string | undefined,
            headers: sink.options.headers as Record<string, string> | undefined,
            timeoutMs: sink.options.timeoutMs as number | undefined,
          }),
        );
      }
    }
  }

  return traceSinks;
}

function resolveRulesPath(
  configPath: string,
  classifiers: ShieldConfig['shield']['classifiers'],
): string | null {
  for (const classifier of classifiers) {
    if (classifier.type === 'deterministic' && typeof classifier.path === 'string') {
      return resolve(dirname(resolve(configPath)), classifier.path);
    }
  }

  return null;
}

function createLlmClassifier(
  classifiers: ShieldConfig['shield']['classifiers'],
): LLMClassifier | null {
  for (const classifier of classifiers) {
    if (classifier.type !== 'llm') {
      continue;
    }

    return new LLMClassifier({
      model: typeof classifier.model === 'string' ? classifier.model : undefined,
      apiKeyEnv:
        typeof classifier.api_key_env === 'string' ? classifier.api_key_env : undefined,
      baseUrlEnv:
        typeof classifier.base_url_env === 'string' ? classifier.base_url_env : undefined,
      timeoutMs:
        typeof classifier.timeout_ms === 'number' ? classifier.timeout_ms : undefined,
      optional:
        typeof classifier.optional === 'boolean' ? classifier.optional : undefined,
      redact: typeof classifier.redact === 'boolean' ? classifier.redact : undefined,
    });
  }

  return null;
}

function mergeSessionContext(context: ToolCallRequest['context'] = {}): ToolCallRequest['context'] {
  const session = sessionStorage.getStore();
  if (!session) {
    return context;
  }

  return {
    ...context,
    conversationId: context.conversationId ?? session.conversationId,
    environment: context.environment ?? session.environment,
    tags: context.tags ?? session.tags,
  };
}

export class Shield {
  readonly id: string;
  readonly name: string;
  readonly policyPath: string;
  private policy: Policy;
  private readonly config: ShieldConfig;
  readonly classifierPipeline: ClassifierPipeline;
  readonly challengeStore: ChallengeStore;
  readonly challengeNotifier: ChallengeNotifier | null;
  private readonly traceSinks: TraceSink[];
  /** NDJSON sink when configured, for backward compatibility. */
  readonly traceSink: NDJSONTraceSink | null;

  private constructor(options: ShieldOptions) {
    this.config = options.config;
    this.policy = options.policy;
    this.policyPath = options.policyPath;
    this.id = options.config.shield.id;
    this.name = options.config.shield.name;
    this.classifierPipeline = options.classifierPipeline ?? new ClassifierPipeline();
    this.challengeStore = options.challengeStore ?? new ChallengeStore();
    this.challengeNotifier = options.challengeNotifier ?? null;

    if (options.traceSinks) {
      this.traceSinks =
        options.traceSinks.length > 1
          ? [new CompositeTraceSink(options.traceSinks)]
          : [...options.traceSinks];
    } else if (options.traceSink) {
      this.traceSinks = [options.traceSink];
    } else {
      this.traceSinks = [];
    }

    this.traceSink =
      this.traceSinks.find((sink): sink is NDJSONTraceSink => sink instanceof NDJSONTraceSink) ??
      null;
  }

  static fromConfigSync(configPath: string): Shield {
    const resolvedConfigPath = resolve(configPath);
    if (!existsSync(resolvedConfigPath)) {
      throw new LexShieldConfigError(`Config file not found: ${resolvedConfigPath}`);
    }

    let parsed: unknown;
    try {
      parsed = parseYaml(readFileSync(resolvedConfigPath, 'utf8'));
    } catch (error) {
      throw new LexShieldConfigError(`Invalid YAML in config: ${resolvedConfigPath}`, {
        cause: error,
      });
    }

    const configResult = ShieldConfigSchema.safeParse(parsed);
    if (!configResult.success) {
      throw new LexShieldConfigError(
        `Config validation failed for ${resolvedConfigPath}: ${configResult.error.message}`,
        { cause: configResult.error },
      );
    }

    const config = configResult.data;
    const policyPath = resolve(dirname(resolvedConfigPath), config.shield.policy);
    const policy = loadPolicyFromFileSync(policyPath);

    const rulesPath = resolveRulesPath(resolvedConfigPath, config.shield.classifiers);
    let deterministicRules = DeterministicRulesSchema.parse({
      version: '1',
      tool_map: {},
      patterns: [],
    });

    if (rulesPath && existsSync(rulesPath)) {
      const rulesParsed = parseYaml(readFileSync(rulesPath, 'utf8'));
      const rulesResult = DeterministicRulesSchema.safeParse(rulesParsed);
      if (!rulesResult.success) {
        throw new LexShieldConfigError(
          `Deterministic rules validation failed for ${rulesPath}: ${rulesResult.error.message}`,
          { cause: rulesResult.error },
        );
      }
      deterministicRules = rulesResult.data;
    }

    const llm = createLlmClassifier(config.shield.classifiers);
    const classifierPipeline = new ClassifierPipeline({
      deterministicRules,
      llm,
      llmEnabled: llm !== null,
    });

    const traceSinks = createTraceSinksFromConfig(resolvedConfigPath, config.shield.sinks);

    return new Shield({
      config,
      policy,
      policyPath,
      classifierPipeline,
      traceSinks,
    });
  }

  static async fromConfig(configPath: string): Promise<Shield> {
    const resolvedConfigPath = resolve(configPath);
    let raw: string;
    try {
      raw = await readFileAsync(resolvedConfigPath, 'utf8');
    } catch (error) {
      throw new LexShieldConfigError(`Failed to read config file: ${resolvedConfigPath}`, {
        cause: error,
      });
    }

    let parsed: unknown;
    try {
      parsed = parseYaml(raw);
    } catch (error) {
      throw new LexShieldConfigError(`Invalid YAML in config: ${resolvedConfigPath}`, {
        cause: error,
      });
    }

    const configResult = ShieldConfigSchema.safeParse(parsed);
    if (!configResult.success) {
      throw new LexShieldConfigError(
        `Config validation failed for ${resolvedConfigPath}: ${configResult.error.message}`,
        { cause: configResult.error },
      );
    }

    const config = configResult.data;
    const policyPath = await resolvePolicyPath(resolvedConfigPath, config.shield.policy);
    const policy = await loadPolicyFromFile(policyPath);

    const rulesPath = resolveRulesPath(resolvedConfigPath, config.shield.classifiers);
    const llm = createLlmClassifier(config.shield.classifiers);
    const classifierPipeline = rulesPath
      ? await ClassifierPipeline.fromRulesPath(rulesPath, {
          llm,
          llmEnabled: llm !== null,
        })
      : new ClassifierPipeline({
          llm,
          llmEnabled: llm !== null,
        });

    const traceSinks = createTraceSinksFromConfig(resolvedConfigPath, config.shield.sinks);

    return new Shield({
      config,
      policy,
      policyPath,
      classifierPipeline,
      traceSinks,
    });
  }

  static fromOptions(options: Omit<ShieldOptions, 'policyPath'> & { policyPath?: string }): Shield {
    return new Shield({
      ...options,
      policyPath: options.policyPath ?? './policy.yaml',
    });
  }

  get policyData(): Policy {
    return this.policy;
  }

  session(options: {
    conversationId?: string;
    environment?: string;
    tags?: Record<string, string>;
  } = {}): ShieldSession {
    return new ShieldSession(options);
  }

  async evaluate(input: EvaluateInput): Promise<Verdict> {
    const startedAt = Date.now();
    const requestId = input.requestId ?? input.id ?? randomUUID();
    const timestamp = input.timestamp ?? new Date().toISOString();

    const request = ToolCallRequestSchema.parse({
      id: requestId,
      shieldId: this.id,
      timestamp,
      caller: input.caller ?? { id: 'anonymous', type: 'agent' },
      tool: { name: input.tool },
      arguments: input.arguments ?? {},
      context: mergeSessionContext(input.context ?? {}),
    });

    const classifications = await this.classifierPipeline.classify(request);
    let verdict = evaluatePolicy(this.policy, { request, classifications }, startedAt);
    verdict = this.attachChallenge(verdict, requestId);

    if (this.traceSinks.length > 0) {
      const payload = buildTracePayload({
        traceId: requestId,
        shieldId: this.id,
        timestamp,
        request,
        classifications,
        verdict,
      });

      for (const sink of this.traceSinks) {
        sink.write(payload);
      }
    }

    return verdict;
  }

  reloadPolicy(): void {
    this.policy = loadPolicyFromFileSync(this.policyPath);
  }

  async reloadPolicyAsync(): Promise<void> {
    this.policy = await loadPolicyFromFile(this.policyPath);
  }

  async recordOutcome(requestId: string, outcome: OutcomeType): Promise<void> {
    for (const sink of this.traceSinks) {
      sink.updateOutcome(requestId, outcome);
    }
  }

  private attachChallenge(verdict: Verdict, requestId: string): Verdict {
    if (verdict.decision !== 'CHALLENGE' && verdict.decision !== 'DEFER') {
      return verdict;
    }

    if (!verdict.matchedRuleId) {
      return verdict;
    }

    const rule = this.policy.rules.find((item) => item.id === verdict.matchedRuleId);
    if (!rule?.challenge) {
      return verdict;
    }

    const challengeId = this.challengeStore.create({
      requestId,
      reason: verdict.reason,
      timeoutSeconds: rule.challenge.timeoutSeconds,
      onTimeout: rule.challenge.onTimeout,
    });

    const record = this.challengeStore.get(challengeId);
    if (record && this.challengeNotifier) {
      const channel = rule.challenge.channel;
      if (channel === 'stdout' || channel === 'webhook') {
        void this.challengeNotifier.notify(record, channel);
      }
    }

    return {
      ...verdict,
      challengeId,
    };
  }

  guard<TArgs extends Record<string, unknown>, TResult>(
    fn: (args: TArgs) => Promise<TResult>,
  ): (args: TArgs) => Promise<TResult>;
  guard<TArgs extends Record<string, unknown>, TResult>(
    toolName: string,
    fn: (args: TArgs) => Promise<TResult>,
    options?: GuardOptions,
  ): (args: TArgs) => Promise<TResult>;
  guard(
    toolName: string,
    options?: GuardOptions,
  ): <TArgs extends Record<string, unknown>, TResult>(
    fn: (args: TArgs) => Promise<TResult>,
  ) => (args: TArgs) => Promise<TResult>;
  guard(
    toolOrFn: string | ((args: Record<string, unknown>) => Promise<unknown>),
    fnOrOptions?: ((args: Record<string, unknown>) => Promise<unknown>) | GuardOptions,
    options: GuardOptions = {},
  ): unknown {
    if (typeof toolOrFn === 'function') {
      return this.wrapGuardedAsync(toolOrFn.name || 'anonymous', toolOrFn, {});
    }

    if (typeof fnOrOptions === 'function') {
      return this.wrapGuardedAsync(toolOrFn, fnOrOptions, options);
    }

    const decoratorOptions = fnOrOptions ?? {};
    return (fn: (args: Record<string, unknown>) => Promise<unknown>) =>
      this.wrapGuardedAsync(toolOrFn, fn, decoratorOptions);
  }

  guardSync<TArgs extends Record<string, unknown>, TResult>(
    fn: (args: TArgs) => TResult,
  ): (args: TArgs) => TResult;
  guardSync<TArgs extends Record<string, unknown>, TResult>(
    toolName: string,
    fn: (args: TArgs) => TResult,
    options?: GuardOptions,
  ): (args: TArgs) => TResult;
  guardSync(
    toolName: string,
    options?: GuardOptions,
  ): <TArgs extends Record<string, unknown>, TResult>(
    fn: (args: TArgs) => TResult,
  ) => (args: TArgs) => TResult;
  guardSync(
    toolOrFn: string | ((args: Record<string, unknown>) => unknown),
    fnOrOptions?: ((args: Record<string, unknown>) => unknown) | GuardOptions,
    options: GuardOptions = {},
  ): unknown {
    if (typeof toolOrFn === 'function') {
      return this.wrapGuardedSync(toolOrFn.name || 'anonymous', toolOrFn, {});
    }

    if (typeof fnOrOptions === 'function') {
      return this.wrapGuardedSync(toolOrFn, fnOrOptions, options);
    }

    const decoratorOptions = fnOrOptions ?? {};
    return (fn: (args: Record<string, unknown>) => unknown) =>
      this.wrapGuardedSync(toolOrFn, fn, decoratorOptions);
  }

  private wrapGuardedAsync<TArgs extends Record<string, unknown>, TResult>(
    toolName: string,
    fn: (args: TArgs) => Promise<TResult>,
    options: GuardOptions,
  ): (args: TArgs) => Promise<TResult> {
    return async (args: TArgs) => {
      const verdict = await this.evaluate({
        tool: toolName,
        arguments: args,
      });
      this.raiseForVerdict(verdict, options);
      return fn(args);
    };
  }

  private wrapGuardedSync<TArgs extends Record<string, unknown>, TResult>(
    toolName: string,
    fn: (args: TArgs) => TResult,
    options: GuardOptions,
  ): (args: TArgs) => TResult {
    return (args: TArgs) => {
      const startedAt = Date.now();
      const request = ToolCallRequestSchema.parse({
        id: randomUUID(),
        shieldId: this.id,
        timestamp: new Date().toISOString(),
        caller: { id: 'anonymous', type: 'agent' },
        tool: { name: toolName },
        arguments: args,
        context: mergeSessionContext({}),
      });

      const classifications = this.classifierPipeline.classifySync(request);
      const verdict = evaluatePolicy(this.policy, { request, classifications }, startedAt);
      this.raiseForVerdict(verdict, options);
      return fn(args);
    };
  }

  private raiseForVerdict(verdict: Verdict, options: GuardOptions): void {
    if (verdict.decision === 'BLOCK') {
      throw new LexShieldBlockedError(verdict.reason, {
        requestId: verdict.requestId,
        verdict,
      });
    }

    if (verdict.decision === 'CHALLENGE') {
      if (options.awaitChallenge) {
        return;
      }
      throw new LexShieldChallengeError(verdict.reason, {
        requestId: verdict.requestId,
        verdict,
      });
    }
  }
}
