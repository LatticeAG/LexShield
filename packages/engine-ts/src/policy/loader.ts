import { readFile } from 'node:fs/promises';
import { parse as parseYaml } from 'yaml';

import { LexShieldConfigError } from '../errors.js';
import { PolicySchema, type Policy } from '../types.js';

function normalizePolicyData(data: Record<string, unknown>): Record<string, unknown> {
  const normalized = { ...data };

  if ('version' in normalized && typeof normalized.version !== 'string') {
    normalized.version = String(normalized.version);
  }

  if (Array.isArray(normalized.rules)) {
    normalized.rules = normalized.rules.map((rule) => {
      if (rule && typeof rule === 'object' && !('name' in rule)) {
        const record = rule as Record<string, unknown>;
        return { ...record, name: record.id ?? 'rule' };
      }
      return rule;
    });
  }

  return normalized;
}

export async function loadPolicyFromFile(path: string): Promise<Policy> {
  let raw: string;
  try {
    raw = await readFile(path, 'utf8');
  } catch (error) {
    throw new LexShieldConfigError(`Failed to read policy file: ${path}`, { cause: error });
  }

  return loadPolicyFromString(raw, path);
}

export function loadPolicyFromString(content: string, source = 'policy'): Policy {
  let parsed: unknown;
  try {
    parsed = parseYaml(content);
  } catch (error) {
    throw new LexShieldConfigError(`Invalid YAML in policy: ${source}`, { cause: error });
  }

  if (!parsed || typeof parsed !== 'object') {
    throw new LexShieldConfigError(`Policy root must be a mapping: ${source}`);
  }

  return loadPolicyFromData(parsed as Record<string, unknown>, source);
}

export function loadPolicyFromData(data: Record<string, unknown>, source = 'policy'): Policy {
  const normalized = normalizePolicyData(data);
  const result = PolicySchema.safeParse(normalized);
  if (!result.success) {
    throw new LexShieldConfigError(
      `Policy validation failed for ${source}: ${result.error.message}`,
      { cause: result.error },
    );
  }

  return result.data;
}

export async function resolvePolicyPath(configPath: string, policyRef: string): Promise<string> {
  const { dirname, resolve } = await import('node:path');
  const baseDir = dirname(resolve(configPath));
  return resolve(baseDir, policyRef);
}
