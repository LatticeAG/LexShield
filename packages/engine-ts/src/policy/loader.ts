import { readFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { parse as parseYaml } from 'yaml';

import { LexShieldConfigError } from '../errors.js';
import { PolicySchema, type Policy } from '../types.js';

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

  const result = PolicySchema.safeParse(parsed);
  if (!result.success) {
    throw new LexShieldConfigError(
      `Policy validation failed for ${source}: ${result.error.message}`,
      { cause: result.error },
    );
  }

  return result.data;
}

export async function resolvePolicyPath(configPath: string, policyRef: string): Promise<string> {
  const baseDir = dirname(resolve(configPath));
  return resolve(baseDir, policyRef);
}
