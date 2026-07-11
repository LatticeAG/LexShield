import { readFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { parse as parseYaml } from 'yaml';

import { runClassifierPipeline } from './classifiers/pipeline.js';
import {
  LexShieldBlockedError,
  LexShieldChallengeError,
  LexShieldConfigError,
} from './errors.js';
import { evaluatePolicy } from './policy/engine.js';
import { loadPolicyFromFile, resolvePolicyPath } from './policy/loader.js';
import {
  DeterministicRulesSchema,
  ShieldConfigSchema,
  ToolCallRequestSchema,
  type Policy,
  type ShieldConfig,
  type ToolCallRequest,
  type Verdict,
} from './types.js';

export interface ShieldOptions {
  config: ShieldConfig;
  policy: Policy;
  deterministicRules?: ReturnType<typeof DeterministicRulesSchema.parse>;
}

export interface EvaluateInput {
  tool: string;
  arguments?: Record<string, unknown>;
  caller?: ToolCallRequest['caller'];
  context?: ToolCallRequest['context'];
  id?: string;
  timestamp?: string;
}

export interface GuardOptions {
  awaitChallenge?: boolean;
}

export class Shield {
  readonly id: string;
  readonly name: string;
  private readonly policy: Policy;
  private readonly config: ShieldConfig;
  private readonly deterministicRules: ReturnType<typeof DeterministicRulesSchema.parse>;

  private constructor(options: ShieldOptions) {
    this.config = options.config;
    this.policy = options.policy;
    this.id = options.config.shield.id;
    this.name = options.config.shield.name;
    this.deterministicRules =
      options.deterministicRules ??
      DeterministicRulesSchema.parse({ version: '1', tool_map: {}, patterns: [] });
  }

  static async fromConfig(configPath: string): Promise<Shield> {
    let raw: string;
    try {
      raw = await readFile(configPath, 'utf8');
    } catch (error) {
      throw new LexShieldConfigError(`Failed to read config file: ${configPath}`, { cause: error });
    }

    let parsed: unknown;
    try {
      parsed = parseYaml(raw);
    } catch (error) {
      throw new LexShieldConfigError(`Invalid YAML in config: ${configPath}`, { cause: error });
    }

    const configResult = ShieldConfigSchema.safeParse(parsed);
    if (!configResult.success) {
      throw new LexShieldConfigError(
        `Config validation failed for ${configPath}: ${configResult.error.message}`,
        { cause: configResult.error },
      );
    }

    const config = configResult.data;
    const policyPath = await resolvePolicyPath(configPath, config.shield.policy);
    const policy = await loadPolicyFromFile(policyPath);

    let deterministicRules = DeterministicRulesSchema.parse({
      version: '1',
      tool_map: {},
      patterns: [],
    });

    const deterministicClassifier = config.shield.classifiers.find(
      (classifier) => classifier.type === 'deterministic',
    );

    if (deterministicClassifier && typeof deterministicClassifier.path === 'string') {
      const rulesPath = resolve(dirname(resolve(configPath)), deterministicClassifier.path);
      const rulesRaw = await readFile(rulesPath, 'utf8');
      const rulesParsed = parseYaml(rulesRaw);
      const rulesResult = DeterministicRulesSchema.safeParse(rulesParsed);
      if (!rulesResult.success) {
        throw new LexShieldConfigError(
          `Deterministic rules validation failed for ${rulesPath}: ${rulesResult.error.message}`,
          { cause: rulesResult.error },
        );
      }
      deterministicRules = rulesResult.data;
    }

    return new Shield({ config, policy, deterministicRules });
  }

  static fromOptions(options: ShieldOptions): Shield {
    return new Shield(options);
  }

  async evaluate(input: EvaluateInput): Promise<Verdict> {
    const startedAt = Date.now();
    const request = ToolCallRequestSchema.parse({
      id: input.id ?? `req-${startedAt}`,
      shieldId: this.id,
      timestamp: input.timestamp ?? new Date().toISOString(),
      caller: input.caller ?? { id: 'anonymous', type: 'agent' },
      tool: { name: input.tool },
      arguments: input.arguments ?? {},
      context: input.context ?? {},
    });

    const classifications = await runClassifierPipeline(request, {
      deterministicRules: this.deterministicRules,
      llmEnabled: this.config.shield.classifiers.some((c) => c.type === 'llm'),
    });

    return evaluatePolicy(
      this.policy,
      { request, classifications },
      startedAt,
    );
  }

  guard<TArgs extends Record<string, unknown>, TResult>(
    toolName: string,
    fn: (args: TArgs) => Promise<TResult>,
    options: GuardOptions = {},
  ): (args: TArgs) => Promise<TResult> {
    return async (args: TArgs) => {
      const verdict = await this.evaluate({
        tool: toolName,
        arguments: args,
      });

      if (verdict.decision === 'BLOCK') {
        throw new LexShieldBlockedError(verdict.reason, {
          requestId: verdict.requestId,
          verdict,
        });
      }

      if (verdict.decision === 'CHALLENGE') {
        if (options.awaitChallenge) {
          // Challenge resolution is not implemented in the scaffold.
        }
        throw new LexShieldChallengeError(verdict.reason, {
          requestId: verdict.requestId,
          verdict,
        });
      }

      return fn(args);
    };
  }
}
