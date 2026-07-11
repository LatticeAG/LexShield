import { readFile } from 'node:fs/promises';
import { parse as parseYaml } from 'yaml';

import { LexShieldConfigError } from '../errors.js';
import {
  DeterministicRulesSchema,
  type Classification,
  type DeterministicRules,
  type ToolCallRequest,
} from '../types.js';

export interface DeterministicClassifierOptions {
  rules?: DeterministicRules;
  rulesPath?: string;
}

function argsBlob(args: Record<string, unknown>): string {
  return Object.values(args)
    .map((value) => String(value))
    .join(' ');
}

function toJsRegex(pattern: string): RegExp {
  if (pattern.startsWith('(?i)')) {
    return new RegExp(pattern.slice(4), 'i');
  }
  return new RegExp(pattern);
}

function matchPattern(
  request: ToolCallRequest,
  patternRule: DeterministicRules['patterns'][number],
): boolean {
  const matchSpec = patternRule.match;

  const anyArgRegex = matchSpec.any_arg_regex;
  if (anyArgRegex && toJsRegex(anyArgRegex).test(argsBlob(request.arguments))) {
    return true;
  }

  for (const [key, value] of Object.entries(request.arguments)) {
    const argRegex = matchSpec[`arg_regex:${key}`];
    if (typeof argRegex === 'string' && toJsRegex(argRegex).test(String(value))) {
      return true;
    }
  }

  return false;
}

export async function loadDeterministicRulesFromFile(path: string): Promise<DeterministicRules> {
  let raw: string;
  try {
    raw = await readFile(path, 'utf8');
  } catch (error) {
    throw new LexShieldConfigError(`Failed to read deterministic rules file: ${path}`, {
      cause: error,
    });
  }

  return loadDeterministicRulesFromString(raw, path);
}

export function loadDeterministicRulesFromString(
  content: string,
  source = 'rules',
): DeterministicRules {
  let parsed: unknown;
  try {
    parsed = parseYaml(content);
  } catch (error) {
    throw new LexShieldConfigError(`Invalid YAML in deterministic rules: ${source}`, {
      cause: error,
    });
  }

  const result = DeterministicRulesSchema.safeParse(parsed ?? {});
  if (!result.success) {
    throw new LexShieldConfigError(
      `Deterministic rules validation failed for ${source}: ${result.error.message}`,
      { cause: result.error },
    );
  }

  return result.data;
}

export function classifyDeterministic(
  request: ToolCallRequest,
  options: DeterministicClassifierOptions,
): Classification | null {
  const rules = options.rules;
  if (!rules) {
    return null;
  }

  for (const patternRule of rules.patterns) {
    if (matchPattern(request, patternRule)) {
      return {
        intent: patternRule.intent,
        confidence: patternRule.confidence,
        alternatives: [],
        classifier: 'deterministic:v1',
      };
    }
  }

  const toolIntent = rules.tool_map[request.tool.name];
  if (toolIntent) {
    return {
      intent: toolIntent,
      confidence: 0.7,
      alternatives: [],
      classifier: 'deterministic:v1',
    };
  }

  return null;
}
