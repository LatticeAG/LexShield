import { describe, expect, it } from 'vitest';

import { LLMCircuitBreaker } from '../src/classifiers/circuit-breaker.js';

describe('LLMCircuitBreaker', () => {
  it('opens after consecutive failures and closes after duration', () => {
    let now = 1_000;
    const breaker = new LLMCircuitBreaker({
      failureThreshold: 3,
      openDurationMs: 10_000,
      now: () => now,
    });

    expect(breaker.isOpen()).toBe(false);
    breaker.recordFailure();
    breaker.recordFailure();
    expect(breaker.isOpen()).toBe(false);

    breaker.recordFailure();
    expect(breaker.isOpen()).toBe(true);

    now += 10_001;
    expect(breaker.isOpen()).toBe(false);
  });

  it('resets failures on success', () => {
    const breaker = new LLMCircuitBreaker({ failureThreshold: 2 });
    breaker.recordFailure();
    breaker.recordSuccess();
    breaker.recordFailure();

    expect(breaker.isOpen()).toBe(false);
  });
});
