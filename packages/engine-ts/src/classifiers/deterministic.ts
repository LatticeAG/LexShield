import type { Classification, DeterministicRules, ToolCallRequest } from '../types.js';

export interface DeterministicClassifierOptions {
  rules: DeterministicRules;
}

function stringifyArgs(args: Record<string, unknown>): string {
  return JSON.stringify(args);
}

function matchAnyArgRegex(args: Record<string, unknown>, pattern: string): boolean {
  const haystack = stringifyArgs(args);
  const regex = new RegExp(pattern);
  return regex.test(haystack);
}

export function classifyDeterministic(
  request: ToolCallRequest,
  options: DeterministicClassifierOptions,
): Classification[] {
  const { rules } = options;
  const toolIntent = rules.tool_map[request.tool.name];

  for (const patternRule of rules.patterns) {
    const regex = patternRule.match.any_arg_regex;
    if (regex && matchAnyArgRegex(request.arguments, regex)) {
      return [
        {
          intent: patternRule.intent,
          confidence: patternRule.confidence,
          alternatives: [],
          classifier: 'deterministic:v1',
          reasoning: `Matched pattern ${patternRule.name}`,
        },
      ];
    }
  }

  if (toolIntent) {
    return [
      {
        intent: toolIntent,
        confidence: 0.7,
        alternatives: [],
        classifier: 'deterministic:v1',
      },
    ];
  }

  return [
    {
      intent: 'unknown.unclassified',
      confidence: 0.2,
      alternatives: [],
      classifier: 'deterministic:v1',
    },
  ];
}
