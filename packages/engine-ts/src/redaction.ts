import { createHash } from 'node:crypto';

export type EmailRedactionMode = 'hash' | 'redact' | 'off';

export interface RedactionOptions {
  /** Default: `hash` for traces, `redact` when sending to LLM. */
  emails?: EmailRedactionMode;
}

const AWS_KEY_PATTERN = /AKIA[0-9A-Z]{16}/g;
const API_KEY_PATTERN = /sk-(?:proj-)?[a-zA-Z0-9]{20,}/g;
const BEARER_TOKEN_PATTERN = /Bearer [A-Za-z0-9._\-]+/g;
const PASSWORD_PATTERN = /password\s*[:=]\s*\S+/gi;
const EMAIL_PATTERN = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;

const REPLACEMENTS: Array<{ pattern: RegExp; replacement: string }> = [
  { pattern: AWS_KEY_PATTERN, replacement: '[REDACTED_AWS_KEY]' },
  { pattern: API_KEY_PATTERN, replacement: '[REDACTED_API_KEY]' },
  { pattern: BEARER_TOKEN_PATTERN, replacement: 'Bearer [REDACTED]' },
  { pattern: PASSWORD_PATTERN, replacement: 'password=[REDACTED]' },
];

function hashEmail(email: string): string {
  const digest = createHash('sha256').update(email.toLowerCase()).digest('hex');
  return `[EMAIL_HASH:${digest.slice(0, 12)}]`;
}

function redactEmails(text: string, mode: EmailRedactionMode): string {
  if (mode === 'off') {
    return text;
  }

  return text.replace(EMAIL_PATTERN, (email) => {
    if (mode === 'hash') {
      return hashEmail(email);
    }
    return '[REDACTED_EMAIL]';
  });
}

/**
 * Apply frozen v0.1 secret redaction patterns (SPEC §9.6).
 */
export function redactText(text: string, options: RedactionOptions = {}): string {
  let result = text;

  for (const { pattern, replacement } of REPLACEMENTS) {
    result = result.replace(pattern, replacement);
  }

  return redactEmails(result, options.emails ?? 'hash');
}

/**
 * Deep-redact unknown values by stringifying leaf nodes.
 */
export function redactValue(value: unknown, options: RedactionOptions = {}): unknown {
  if (value === null || value === undefined) {
    return value;
  }

  if (typeof value === 'string') {
    return redactText(value, options);
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => redactValue(item, options));
  }

  if (typeof value === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value)) {
      result[key] = redactValue(nested, options);
    }
    return result;
  }

  return redactText(String(value), options);
}

export function redactArguments(
  args: Record<string, unknown>,
  options: RedactionOptions = {},
): Record<string, unknown> {
  return redactValue(args, options) as Record<string, unknown>;
}

export const REDACTION_PATTERNS = [
  'AKIA[0-9A-Z]{16}',
  'sk-(?:proj-)?[a-zA-Z0-9]{20,}',
  'Bearer [A-Za-z0-9._\\-]+',
  'password\\s*[:=]\\s*\\S+',
] as const;
