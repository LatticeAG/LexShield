export { VERSION } from './version.js';

export {
  LexShieldBlockedError,
  LexShieldChallengeError,
  LexShieldConfigError,
  LexShieldError,
  type LexShieldErrorCode,
} from './errors.js';

export {
  redactArguments,
  redactText,
  redactValue,
  REDACTION_PATTERNS,
  type EmailRedactionMode,
  type RedactionOptions,
} from './redaction.js';

export { Shield, type EvaluateInput, type GuardOptions, type ShieldOptions } from './shield.js';

export { loadPolicyFromFile, loadPolicyFromString, loadPolicyFromData, resolvePolicyPath } from './policy/loader.js';
export { evaluatePolicy, type PolicyEvaluationInput } from './policy/engine.js';
export { Expression, ExpressionError, buildExpressionBindings } from './policy/expressions.js';

export {
  classifyDeterministic,
  loadDeterministicRulesFromFile,
  loadDeterministicRulesFromString,
} from './classifiers/deterministic.js';
export { runClassifierPipeline, type ClassifierPipelineOptions } from './classifiers/pipeline.js';

export {
  CallerSchema,
  CallerTypeSchema,
  CallContextSchema,
  ChallengeConfigSchema,
  ClassificationSchema,
  DeterministicRulesSchema,
  OutcomeTypeSchema,
  PolicyRuleSchema,
  PolicySchema,
  PriorCallSchema,
  RuleMatchSchema,
  ShieldConfigSchema,
  SinkConfigSchema,
  ToolCallRequestSchema,
  ToolRefSchema,
  TraceSchema,
  UpstreamConfigSchema,
  VerdictSchema,
  VerdictTypeSchema,
  type Caller,
  type CallerType,
  type CallContext,
  type ChallengeConfig,
  type Classification,
  type DeterministicRules,
  type OutcomeType,
  type Policy,
  type PolicyRule,
  type PriorCall,
  type RuleMatch,
  type ShieldConfig,
  type SinkConfig,
  type ToolCallRequest,
  type ToolRef,
  type Trace,
  type UpstreamConfig,
  type Verdict,
  type VerdictType,
} from './types.js';
