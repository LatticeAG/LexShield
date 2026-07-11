import { createHash } from 'node:crypto';

import { classifyDeterministic, loadDeterministicRulesFromFile } from './deterministic.js';
import { getDefaultCircuitBreaker, type LLMCircuitBreaker } from './circuit-breaker.js';
import { LLMClassifier } from './llm.js';
import { getIntentSeverity, type Taxonomy, builtinTaxonomy } from '../taxonomy.js';
import type { Classification, DeterministicRules, ToolCallRequest } from '../types.js';

export const DETERMINISTIC_SKIP_LLM_THRESHOLD = 0.9;
export const UNKNOWN_INTENT = 'unknown.unclassified';
export const CACHE_TTL_MS = 60_000;

export interface ClassifierPipelineOptions {
  deterministicRules?: DeterministicRules;
  rulesPath?: string;
  llm?: LLMClassifier | null;
  llmEnabled?: boolean;
  taxonomy?: Taxonomy;
  classifierIds?: string[];
  cacheEnabled?: boolean;
  circuitBreaker?: LLMCircuitBreaker;
}

interface CacheEntry {
  expiresAt: number;
  classifications: Classification[];
}

const classificationCache = new Map<string, CacheEntry>();

function isDeterministicClassifier(classifier: string): boolean {
  return classifier.startsWith('deterministic');
}

function pickPrimaryClassification(classifications: Classification[], taxonomy: Taxonomy): Classification {
  return classifications.reduce((best, current) => {
    const bestSeverity = getIntentSeverity(best.intent, taxonomy);
    const currentSeverity = getIntentSeverity(current.intent, taxonomy);

    if (currentSeverity > bestSeverity) {
      return current;
    }
    if (currentSeverity < bestSeverity) {
      return best;
    }

    if (current.confidence > best.confidence) {
      return current;
    }
    if (current.confidence < best.confidence) {
      return best;
    }

    const currentIsDeterministic = isDeterministicClassifier(current.classifier);
    const bestIsDeterministic = isDeterministicClassifier(best.classifier);
    if (currentIsDeterministic && !bestIsDeterministic) {
      return current;
    }

    return best;
  });
}

export function mergeClassifications(
  classifications: Classification[],
  taxonomy: Taxonomy = builtinTaxonomy(),
): Classification[] {
  if (classifications.length <= 1) {
    return [...classifications];
  }

  const primary = pickPrimaryClassification(classifications, taxonomy);
  const rest = classifications.filter((item) => item !== primary);
  return [primary, ...rest];
}

function isCacheable(request: ToolCallRequest): boolean {
  const context = request.context;
  return !(context.messages?.length || context.priorCalls?.length);
}

function buildCacheKey(
  request: ToolCallRequest,
  taxonomy: Taxonomy,
  classifierIds: string[],
): string {
  const sortedArgs = JSON.stringify(request.arguments, Object.keys(request.arguments).sort());
  const payload = [
    request.tool.name,
    sortedArgs,
    taxonomy.version,
    classifierIds.join(','),
  ].join('|');

  return createHash('sha256').update(payload).digest('hex');
}

function readCache(key: string): Classification[] | null {
  const entry = classificationCache.get(key);
  if (!entry) {
    return null;
  }

  if (Date.now() > entry.expiresAt) {
    classificationCache.delete(key);
    return null;
  }

  return entry.classifications.map((classification) => ({ ...classification }));
}

function writeCache(key: string, classifications: Classification[]): void {
  classificationCache.set(key, {
    expiresAt: Date.now() + CACHE_TTL_MS,
    classifications: classifications.map((classification) => ({ ...classification })),
  });
}

export function clearClassificationCache(): void {
  classificationCache.clear();
}

export class ClassifierPipeline {
  private readonly deterministicRules?: DeterministicRules;
  private readonly llm: LLMClassifier | null;
  private readonly taxonomy: Taxonomy;
  private readonly classifierIds: string[];
  private readonly cacheEnabled: boolean;
  private readonly circuitBreaker: LLMCircuitBreaker;

  constructor(options: ClassifierPipelineOptions = {}) {
    this.deterministicRules = options.deterministicRules;
    this.llm = options.llmEnabled === false ? null : (options.llm ?? new LLMClassifier());
    this.taxonomy = options.taxonomy ?? builtinTaxonomy();
    this.classifierIds = options.classifierIds ?? [
      'deterministic:v1',
      this.llm ? `llm:openai:${this.llm.model}` : 'llm:disabled',
    ];
    this.cacheEnabled = options.cacheEnabled ?? true;
    this.circuitBreaker = options.circuitBreaker ?? getDefaultCircuitBreaker();
  }

  static async fromRulesPath(
    rulesPath: string | null | undefined,
    options: Omit<ClassifierPipelineOptions, 'deterministicRules' | 'rulesPath'> = {},
  ): Promise<ClassifierPipeline> {
    if (!rulesPath) {
      return new ClassifierPipeline(options);
    }

    const deterministicRules = await loadDeterministicRulesFromFile(rulesPath);
    return new ClassifierPipeline({ ...options, deterministicRules, rulesPath });
  }

  async classify(request: ToolCallRequest): Promise<Classification[]> {
    const cacheKey =
      this.cacheEnabled && isCacheable(request)
        ? buildCacheKey(request, this.taxonomy, this.classifierIds)
        : null;

    if (cacheKey) {
      const cached = readCache(cacheKey);
      if (cached) {
        return cached;
      }
    }

    const results: Classification[] = [];

    const deterministic = classifyDeterministic(request, {
      rules: this.deterministicRules,
    });

    if (deterministic) {
      results.push(deterministic);
      if (deterministic.confidence >= DETERMINISTIC_SKIP_LLM_THRESHOLD) {
        const merged = mergeClassifications(results, this.taxonomy);
        if (cacheKey) {
          writeCache(cacheKey, merged);
        }
        return merged;
      }
    }

    if (this.llm?.isAvailable() && !this.circuitBreaker.isOpen()) {
      const llmResult = await this.llm.classify(request);
      if (llmResult) {
        this.circuitBreaker.recordSuccess();
        results.push(llmResult);
      } else {
        this.circuitBreaker.recordFailure();
      }
    }

    if (results.length === 0) {
      results.push({
        intent: UNKNOWN_INTENT,
        confidence: 0.5,
        alternatives: [],
        classifier: 'deterministic:v1',
        reasoning: 'No deterministic or LLM classification',
      });
    }

    const merged = mergeClassifications(results, this.taxonomy);
    if (cacheKey) {
      writeCache(cacheKey, merged);
    }
    return merged;
  }

  classifySync(request: ToolCallRequest): Classification[] {
    const results: Classification[] = [];

    const deterministic = classifyDeterministic(request, {
      rules: this.deterministicRules,
    });

    if (deterministic) {
      results.push(deterministic);
    }

    if (results.length === 0) {
      results.push({
        intent: UNKNOWN_INTENT,
        confidence: 0.5,
        alternatives: [],
        classifier: 'deterministic:v1',
        reasoning: 'No deterministic or LLM classification',
      });
    }

    return mergeClassifications(results, this.taxonomy);
  }
}

export async function runClassifierPipeline(
  request: ToolCallRequest,
  options: ClassifierPipelineOptions = {},
): Promise<Classification[]> {
  const pipeline = new ClassifierPipeline(options);
  return pipeline.classify(request);
}
