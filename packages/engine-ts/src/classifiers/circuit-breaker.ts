export interface LLMCircuitBreakerOptions {
  failureThreshold?: number;
  openDurationMs?: number;
  now?: () => number;
}

/**
 * Circuit breaker for LLM classifier calls.
 * After N consecutive failures, skip LLM calls for T seconds.
 */
export class LLMCircuitBreaker {
  private readonly failureThreshold: number;
  private readonly openDurationMs: number;
  private readonly now: () => number;
  private consecutiveFailures = 0;
  private openedAt: number | null = null;

  constructor(options: LLMCircuitBreakerOptions = {}) {
    this.failureThreshold = options.failureThreshold ?? 3;
    this.openDurationMs = options.openDurationMs ?? 60_000;
    this.now = options.now ?? Date.now;
  }

  isOpen(): boolean {
    if (this.openedAt === null) {
      return false;
    }

    if (this.now() - this.openedAt >= this.openDurationMs) {
      this.openedAt = null;
      this.consecutiveFailures = 0;
      return false;
    }

    return true;
  }

  recordSuccess(): void {
    this.consecutiveFailures = 0;
    this.openedAt = null;
  }

  recordFailure(): void {
    this.consecutiveFailures += 1;
    if (this.consecutiveFailures >= this.failureThreshold) {
      this.openedAt = this.now();
    }
  }

  reset(): void {
    this.consecutiveFailures = 0;
    this.openedAt = null;
  }
}

let defaultCircuitBreaker: LLMCircuitBreaker | null = null;

export function getDefaultCircuitBreaker(): LLMCircuitBreaker {
  if (!defaultCircuitBreaker) {
    defaultCircuitBreaker = new LLMCircuitBreaker();
  }
  return defaultCircuitBreaker;
}

export function resetDefaultCircuitBreaker(): void {
  defaultCircuitBreaker?.reset();
  defaultCircuitBreaker = null;
}
