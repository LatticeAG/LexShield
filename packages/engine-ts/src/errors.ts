import type { Verdict } from './types.js';

export type LexShieldErrorCode =
  | 'lexshield_blocked'
  | 'lexshield_challenged'
  | 'lexshield_deferred'
  | 'lexshield_config'
  | 'lexshield_upstream';

export class LexShieldError extends Error {
  readonly code: LexShieldErrorCode;
  readonly requestId?: string;
  readonly verdict?: Verdict;

  constructor(
    message: string,
    code: LexShieldErrorCode,
    options?: { requestId?: string; verdict?: Verdict; cause?: unknown },
  ) {
    super(message, { cause: options?.cause });
    this.name = 'LexShieldError';
    this.code = code;
    this.requestId = options?.requestId;
    this.verdict = options?.verdict;
  }
}

export class LexShieldBlockedError extends LexShieldError {
  constructor(message: string, options?: { requestId?: string; verdict?: Verdict }) {
    super(message, 'lexshield_blocked', options);
    this.name = 'LexShieldBlockedError';
  }
}

export class LexShieldChallengeError extends LexShieldError {
  constructor(message: string, options?: { requestId?: string; verdict?: Verdict }) {
    super(message, 'lexshield_challenged', options);
    this.name = 'LexShieldChallengeError';
  }
}

export class LexShieldConfigError extends LexShieldError {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, 'lexshield_config', { cause: options?.cause });
    this.name = 'LexShieldConfigError';
  }
}
