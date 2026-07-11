import { existsSync, readFileSync } from 'node:fs';
import { readFile as readFileAsync } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { AsyncLocalStorage } from 'node:async_hooks';
import { randomUUID } from 'node:crypto';
import { parse as parseYaml } from 'yaml';

import { ChallengeStore } from './challenges/store.js';
import { ClassifierPipeline } from './classifiers/pipeline.js';
import {
  LexShieldBlockedError,
  LexShieldChallengeError,
  LexShieldConfigError,
} from './errors.js';
import { evaluatePolicy } from './policy/engine.js';
import { loadPolicyFromFile, loadPolicyFromFileSync, resolvePolicyPath } from './policy/loader.js';
import { NDJSONTraceSink } from './traces/sink.js';
import {
  DeterministicRulesSchema,
  ShieldConfigSchema,
  ToolCallRequestSchema,
  type OutcomeType,
  type Policy,
  type ShieldConfig,
  type ToolCallRequest,
  type Trace,
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

function resolveTraceSinkPath(
  configPath: string,
  sinks: ShieldConfig['shield']['sinks'],
): string | null {
  for (const sink of sinks) {
    if (sink.type !== 'file') {
      continue;
    }

    const sinkRecord = sink as { path?: string; options?: { path?: string } };
    const relativePath = sinkRecord.path ?? sinkRecord.options?.path ?? './traces.ndjson';
    return resolve(dirname(resolve(configPath)), relativePath);
  }

  return null;
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
  readonly traceSink: NDJSONTraceSink | null;

  private constructor(options: ShieldOptions) {
    this.config = options.config;
    this.policy = options.policy;
    this.policyPath = options.policyPath;
    this.id = options.config.shield.id;
    this.name = options.config.shield.name;
    this.classifierPipeline = options.classifierPipeline ?? new ClassifierPipeline();
    this.challengeStore = options.challengeStore ?? new ChallengeStore();
    this.traceSink = options.traceSink ?? null;
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

    const llmEnabled = config.shield.classifiers.some((classifier) => classifier.type === 'llm');
    const classifierPipeline = new ClassifierPipeline({
      deterministicRules,
      llmEnabled,
    });

    const traceSinkPath = resolveTraceSinkPath(resolvedConfigPath, config.shield.sinks);
    const traceSink = traceSinkPath ? new NDJSONTraceSink(traceSinkPath) : null;

    return new Shield({
      config,
      policy,
      policyPath,
      classifierPipeline,
      traceSink,
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
    const classifierPipeline = rulesPath
      ? await ClassifierPipeline.fromRulesPath(rulesPath, {
          llmEnabled: config.shield.classifiers.some((classifier) => classifier.type === 'llm'),
        })
      : new ClassifierPipeline({
          llmEnabled: config.shield.classifiers.some((classifier) => classifier.type === 'llm'),
        });

    const traceSinkPath = resolveTraceSinkPath(resolvedConfigPath, config.shield.sinks);
    const traceSink = traceSinkPath ? new NDJSONTraceSink(traceSinkPath) : null;

    return new Shield({
      config,
      policy,
      policyPath,
      classifierPipeline,
      traceSink,
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

    const request = ToolCallRequestSchema.parse({
      id: requestId,
      shieldId: this.id,
      timestamp: input.timestamp ?? new Date().toISOString(),
      caller: input.caller ?? { id: 'anonymous', type: 'agent' },
      tool: { name: input.tool },
      arguments: input.arguments ?? {},
      context: mergeSessionContext(input.context ?? {}),
    });

    const classifications = await this.classifierPipeline.classify(request);
    const verdict = evaluatePolicy(
      this.policy,
      { request, classifications },
      startedAt,
    );

    if (this.traceSink) {
      const trace: Trace = {
        id: requestId,
        request,
        verdict,
      };
      this.traceSink.write(trace);
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
    if (this.traceSink) {
      this.traceSink.updateOutcome(requestId, outcome);
    }
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

