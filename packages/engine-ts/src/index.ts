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

export { LocalApiClient, type EvaluateApiInput, type LocalApiClientOptions } from './client.js';

export {
  Shield,
  ShieldSession,
  type EvaluateInput,
  type GuardOptions,
  type ShieldOptions,
} from './shield.js';

export {
  loadPolicyFromFile,
  loadPolicyFromFileSync,
  loadPolicyFromString,
  loadPolicyFromData,
  resolvePolicyPath,
} from './policy/loader.js';
export { evaluatePolicy, type PolicyEvaluationInput } from './policy/engine.js';
export { Expression, ExpressionError, buildExpressionBindings } from './policy/expressions.js';

export {
  classifyDeterministic,
  loadDeterministicRulesFromFile,
  loadDeterministicRulesFromString,
} from './classifiers/deterministic.js';
export { LLMClassifier, type LLMClassifierOptions } from './classifiers/llm.js';
export {
  ClassifierPipeline,
  runClassifierPipeline,
  mergeClassifications,
  clearClassificationCache,
  DETERMINISTIC_SKIP_LLM_THRESHOLD,
  UNKNOWN_INTENT,
  CACHE_TTL_MS,
  type ClassifierPipelineOptions,
} from './classifiers/pipeline.js';

export {
  BUILTIN_INTENT_SEVERITY,
  BUILTIN_TAXONOMY_VERSION,
  builtinTaxonomy,
  getIntentSeverity,
  mergeTaxonomy,
  type Taxonomy,
} from './taxonomy.js';

export { NDJSONTraceSink } from './traces/sink.js';
export { ChallengeStore, type ChallengeRecord } from './challenges/store.js';

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
