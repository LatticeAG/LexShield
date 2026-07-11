import type { Classification, Policy, PolicyRule, ToolCallRequest, Verdict } from '../types.js';
import {
  Expression,
  buildExpressionBindings,
  type ExpressionBindings,
} from './expressions.js';

export interface PolicyEvaluationInput {
  request: ToolCallRequest;
  classifications: Classification[];
}

const UNKNOWN_INTENT = 'unknown.unclassified';
const expressionCache = new Map<string, Expression>();

function getExpression(source: string): Expression {
  let compiled = expressionCache.get(source);
  if (!compiled) {
    compiled = Expression.parse(source);
    expressionCache.set(source, compiled);
  }
  return compiled;
}

function globMatch(pattern: string, value: string): boolean {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*');
  const regex = new RegExp(`^${escaped}$`);
  return regex.test(value);
}

function matchingIntents(classifications: Classification[]): Set<string> {
  const intents = new Set<string>();
  const primary = classifications[0];
  if (!primary) {
    return intents;
  }

  intents.add(primary.intent);
  for (const alternative of primary.alternatives) {
    intents.add(alternative.intent);
  }

  return intents;
}

function tagsMatch(
  requiredTags: Record<string, string[]>,
  contextTags: Record<string, string> | undefined,
): boolean {
  if (contextTags === undefined) {
    return false;
  }

  for (const [key, allowedValues] of Object.entries(requiredTags)) {
    const actual = contextTags[key];
    if (actual === undefined || !allowedValues.includes(actual)) {
      return false;
    }
  }

  return true;
}

function ruleMatches(
  rule: PolicyRule,
  input: PolicyEvaluationInput,
  bindings: ExpressionBindings,
): boolean {
  const { request, classifications } = input;
  const primary = classifications[0];
  const match = rule.match;

  if (match.tools?.length) {
    const toolName = request.tool.name;
    const matched = match.tools.some((pattern) => globMatch(pattern, toolName));
    if (!matched) {
      return false;
    }
  }

  if (match.intents?.length) {
    const intents = matchingIntents(classifications);
    const matched = match.intents.some((intent) => intents.has(intent));
    if (!matched) {
      return false;
    }
  }

  if (match.environments?.length) {
    const env = request.context.environment;
    if (!env || !match.environments.includes(env)) {
      return false;
    }
  }

  if (match.callers?.length) {
    if (!match.callers.includes(request.caller.id)) {
      return false;
    }
  }

  if (match.roles?.length) {
    const roles = request.caller.roles ?? [];
    const matched = match.roles.some((role) => roles.includes(role));
    if (!matched) {
      return false;
    }
  }

  if (match.tags && Object.keys(match.tags).length > 0) {
    if (!tagsMatch(match.tags, request.context.tags)) {
      return false;
    }
  }

  if (match.minConfidence !== undefined) {
    if (!primary || primary.confidence < match.minConfidence) {
      return false;
    }
  }

  if (match.expression) {
    try {
      if (!getExpression(match.expression).evaluate(bindings)) {
        return false;
      }
    } catch {
      return false;
    }
  }

  return true;
}

function sortRules(rules: PolicyRule[]): PolicyRule[] {
  return [...rules]
    .filter((rule) => rule.enabled !== false)
    .sort((a, b) => {
      if (b.priority !== a.priority) {
        return b.priority - a.priority;
      }
      return a.id.localeCompare(b.id);
    });
}

export function evaluatePolicy(
  policy: Policy,
  input: PolicyEvaluationInput,
  startedAt = Date.now(),
): Verdict {
  const primary = input.classifications[0];
  const bindings = buildExpressionBindings(input.request, input.classifications);
  const sorted = sortRules(policy.rules);
  const matchedRule = sorted.find((rule) => ruleMatches(rule, input, bindings));

  if (matchedRule) {
    return {
      requestId: input.request.id,
      decision: matchedRule.verdict,
      matchedRuleId: matchedRule.id,
      reason: matchedRule.reason,
      classifications: input.classifications,
      durationMs: Date.now() - startedAt,
      policyVersion: policy.version,
      challengeId:
        matchedRule.verdict === 'CHALLENGE' ? `challenge-${input.request.id}` : undefined,
    };
  }

  if (!primary || primary.intent === UNKNOWN_INTENT) {
    return {
      requestId: input.request.id,
      decision: 'BLOCK',
      reason: 'No matching policy rule; default deny for unclassified intent',
      classifications: input.classifications,
      durationMs: Date.now() - startedAt,
      policyVersion: policy.version,
    };
  }

  const decision = policy.defaultVerdict;
  return {
    requestId: input.request.id,
    decision,
    reason: `No matching rule; applied default verdict ${decision}`,
    classifications: input.classifications,
    durationMs: Date.now() - startedAt,
    policyVersion: policy.version,
  };
}
