import { z } from 'zod';

export const VerdictTypeSchema = z.enum(['ALLOW', 'BLOCK', 'CHALLENGE', 'DEFER']);
export type VerdictType = z.infer<typeof VerdictTypeSchema>;

export const CallerTypeSchema = z.enum(['user', 'agent', 'service_account']);
export type CallerType = z.infer<typeof CallerTypeSchema>;

export const OutcomeTypeSchema = z.enum([
  'EXECUTED',
  'BLOCKED',
  'CHALLENGED',
  'DEFERRED',
  'ERROR',
  'APPROVED_EXECUTED',
  'DENIED',
]);
export type OutcomeType = z.infer<typeof OutcomeTypeSchema>;

export const ChallengeConfigSchema = z.object({
  channel: z.enum(['stdout', 'webhook', 'slack', 'dashboard']),
  timeoutSeconds: z.number().int().positive(),
  onTimeout: z.enum(['BLOCK', 'ALLOW']),
  reviewers: z.array(z.string()).optional(),
});
export type ChallengeConfig = z.infer<typeof ChallengeConfigSchema>;

export const RuleMatchSchema = z.object({
  intents: z.array(z.string()).optional(),
  tools: z.array(z.string()).optional(),
  callers: z.array(z.string()).optional(),
  roles: z.array(z.string()).optional(),
  environments: z.array(z.string()).optional(),
  tags: z.record(z.array(z.string())).optional(),
  minConfidence: z.number().min(0).max(1).optional(),
  expression: z.string().optional(),
});
export type RuleMatch = z.infer<typeof RuleMatchSchema>;

export const PolicyRuleSchema = z.object({
  id: z.string(),
  name: z.string(),
  priority: z.number(),
  enabled: z.boolean().optional(),
  match: RuleMatchSchema,
  verdict: VerdictTypeSchema,
  reason: z.string(),
  challenge: ChallengeConfigSchema.optional(),
});
export type PolicyRule = z.infer<typeof PolicyRuleSchema>;

export const PolicySchema = z.object({
  id: z.string(),
  name: z.string(),
  version: z.union([z.string(), z.number()]).transform(String),
  description: z.string().optional(),
  defaultVerdict: VerdictTypeSchema,
  rules: z.array(PolicyRuleSchema),
  taxonomyRef: z.string().optional(),
  severity_threshold: z
    .object({
      alternatives_min_confidence: z.number().min(0).max(1).optional(),
    })
    .optional(),
});
export type Policy = z.infer<typeof PolicySchema>;

export const CallerSchema = z.object({
  id: z.string(),
  type: CallerTypeSchema,
  roles: z.array(z.string()).optional(),
  metadata: z.record(z.unknown()).optional(),
});
export type Caller = z.infer<typeof CallerSchema>;

export const ToolRefSchema = z.object({
  name: z.string(),
  namespace: z.string().optional(),
  version: z.string().optional(),
});
export type ToolRef = z.infer<typeof ToolRefSchema>;

export const PriorCallSchema = z.object({
  timestamp: z.string(),
  tool: ToolRefSchema,
  intent: z.string(),
  verdict: VerdictTypeSchema,
});
export type PriorCall = z.infer<typeof PriorCallSchema>;

export const CallContextSchema = z.object({
  conversationId: z.string().optional(),
  messages: z
    .array(
      z.object({
        role: z.string(),
        content: z.string(),
      }),
    )
    .optional(),
  priorCalls: z.array(PriorCallSchema).optional(),
  environment: z.string().optional(),
  tags: z.record(z.string()).optional(),
});
export type CallContext = z.infer<typeof CallContextSchema>;

export const ToolCallRequestSchema = z.object({
  id: z.string(),
  shieldId: z.string(),
  timestamp: z.string(),
  caller: CallerSchema,
  tool: ToolRefSchema,
  arguments: z.record(z.unknown()),
  context: CallContextSchema,
});
export type ToolCallRequest = z.infer<typeof ToolCallRequestSchema>;

export const ClassificationSchema = z.object({
  intent: z.string(),
  confidence: z.number().min(0).max(1),
  alternatives: z.array(
    z.object({
      intent: z.string(),
      confidence: z.number().min(0).max(1),
    }),
  ),
  classifier: z.string(),
  reasoning: z.string().optional(),
  signalsUsed: z.array(z.string()).optional(),
});
export type Classification = z.infer<typeof ClassificationSchema>;

export const VerdictSchema = z.object({
  requestId: z.string(),
  decision: VerdictTypeSchema,
  matchedRuleId: z.string().optional(),
  reason: z.string(),
  classifications: z.array(ClassificationSchema),
  durationMs: z.number().nonnegative(),
  challengeId: z.string().optional(),
  policyVersion: z.string().optional(),
});
export type Verdict = z.infer<typeof VerdictSchema>;

export const TraceSchema = z.object({
  id: z.string(),
  request: ToolCallRequestSchema,
  verdict: VerdictSchema,
  outcome: OutcomeTypeSchema.optional(),
  outcomeAt: z.string().optional(),
  redactions: z.array(z.string()).optional(),
  metadata: z.record(z.unknown()).optional(),
});
export type Trace = z.infer<typeof TraceSchema>;

export const SinkConfigSchema = z.object({
  type: z.enum(['stdout', 'file', 'http', 'otlp']),
  path: z.string().optional(),
  options: z.record(z.unknown()).default({}),
});
export type SinkConfig = z.infer<typeof SinkConfigSchema>;

export const UpstreamConfigSchema = z.object({
  url: z.string().url(),
  headers: z.record(z.string()).optional(),
  timeoutMs: z.number().int().positive().optional(),
});
export type UpstreamConfig = z.infer<typeof UpstreamConfigSchema>;

export const ShieldConfigSchema = z.object({
  version: z.union([z.string(), z.number()]).transform(String),
  shield: z.object({
    id: z.string(),
    name: z.string(),
    policy: z.string(),
    taxonomy: z.string().optional(),
    classifiers: z.array(z.record(z.unknown())).default([]),
    fail_on_classifier_error: VerdictTypeSchema.optional(),
    sinks: z.array(SinkConfigSchema).default([]),
    proxy: z
      .object({
        enabled: z.boolean().default(false),
        upstreams: z.record(UpstreamConfigSchema).optional(),
      })
      .optional(),
  }),
  server: z
    .object({
      host: z.string().default('127.0.0.1'),
      port: z.number().int().positive().default(8787),
      token_env: z.string().optional(),
    })
    .optional(),
});
export type ShieldConfig = z.infer<typeof ShieldConfigSchema>;

export const DeterministicRulesSchema = z.object({
  version: z.union([z.string(), z.number()]).transform(String),
  tool_map: z.record(z.string()).default({}),
  patterns: z
    .array(
      z.object({
        name: z.string(),
        match: z.object({
          any_arg_regex: z.string().optional(),
        }).passthrough(),
        intent: z.string(),
        confidence: z.number().min(0).max(1),
      }),
    )
    .default([]),
});
export type DeterministicRules = z.infer<typeof DeterministicRulesSchema>;
