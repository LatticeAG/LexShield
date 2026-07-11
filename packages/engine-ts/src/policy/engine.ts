import type { Classification, Policy, PolicyRule, ToolCallRequest, Verdict } from '../types.js';

export interface PolicyEvaluationInput {
  request: ToolCallRequest;
  classifications: Classification[];
}

function ruleMatches(rule: PolicyRule, input: PolicyEvaluationInput): boolean {
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
    const intents = new Set([
      ...(primary ? [primary.intent] : []),
      ...classifications.flatMap((c) => c.alternatives.map((a) => a.intent)),
    ]);
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

  if (match.minConfidence !== undefined && primary) {
    if (primary.confidence < match.minConfidence) {
      return false;
    }
  }

  // Expression evaluation is not implemented in the scaffold.
  if (match.expression) {
    return false;
  }

  return true;
}

function globMatch(pattern: string, value: string): boolean {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*');
  const regex = new RegExp(`^${escaped}$`);
  return regex.test(value);
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
  const sorted = sortRules(policy.rules);
  const matchedRule = sorted.find((rule) => ruleMatches(rule, input));

  const decision = matchedRule?.verdict ?? policy.defaultVerdict;
  const reason =
    matchedRule?.reason ??
    (decision === policy.defaultVerdict
      ? 'No matching rule; applied default verdict'
      : 'No matching rule');

  return {
    requestId: input.request.id,
    decision,
    matchedRuleId: matchedRule?.id,
    reason,
    classifications: input.classifications,
    durationMs: Date.now() - startedAt,
    policyVersion: policy.version,
    challengeId: decision === 'CHALLENGE' ? `challenge-${input.request.id}` : undefined,
  };
}
