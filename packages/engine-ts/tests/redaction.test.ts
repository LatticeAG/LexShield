import { describe, expect, it } from 'vitest';

import { redactArguments, redactText } from '../src/redaction.js';

describe('redactText', () => {
  it('redacts AWS access keys', () => {
    const input = 'key=AKIAIOSFODNN7EXAMPLE in body';
    expect(redactText(input)).toBe('key=[REDACTED_AWS_KEY] in body');
  });

  it('redacts OpenAI-style API keys', () => {
    expect(redactText('token sk-abcdefghijklmnopqrstuvwxyz123456')).toBe(
      'token [REDACTED_API_KEY]',
    );
    expect(redactText('token sk-proj-abcdefghijklmnopqrstuvwxyz123456')).toBe(
      'token [REDACTED_API_KEY]',
    );
  });

  it('redacts bearer tokens', () => {
    expect(redactText('Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc')).toBe(
      'Authorization: Bearer [REDACTED]',
    );
  });

  it('redacts password assignments case-insensitively', () => {
    expect(redactText('db PASSWORD: s3cret!')).toBe('db password=[REDACTED]');
    expect(redactText('db password= s3cret!')).toBe('db password=[REDACTED]');
  });

  it('hashes emails by default', () => {
    const result = redactText('contact user@example.com please');
    expect(result).toMatch(/contact \[EMAIL_HASH:[a-f0-9]{12}\] please/);
    expect(result).not.toContain('user@example.com');
  });

  it('fully redacts emails when configured', () => {
    expect(redactText('contact user@example.com please', { emails: 'redact' })).toBe(
      'contact [REDACTED_EMAIL] please',
    );
  });
});

describe('redactArguments', () => {
  it('redacts nested secret values in argument objects', () => {
    const redacted = redactArguments({
      to: 'ops@example.com',
      body: 'rotate AKIAIOSFODNN7EXAMPLE now',
      nested: {
        token: 'Bearer abc.def-ghi',
      },
    });

    expect(redacted.body).toBe('rotate [REDACTED_AWS_KEY] now');
    expect(redacted.nested).toEqual({ token: 'Bearer [REDACTED]' });
    expect(String(redacted.to)).toMatch(/\[EMAIL_HASH:[a-f0-9]{12}\]/);
  });
});
