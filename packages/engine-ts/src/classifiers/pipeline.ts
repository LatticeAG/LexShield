import { classifyDeterministic } from './deterministic.js';
import type { Classification, DeterministicRules, ToolCallRequest } from '../types.js';

const DETERMINISTIC_SKIP_LLM_THRESHOLD = 0.9;
export const UNKNOWN_INTENT = 'unknown.unclassified';

export interface ClassifierPipelineOptions {
  deterministicRules?: DeterministicRules;
  llmEnabled?: boolean;
}

export async function runClassifierPipeline(
  request: ToolCallRequest,
  options: ClassifierPipelineOptions = {},
): Promise<Classification[]> {
  const results: Classification[] = [];

  const deterministic = classifyDeterministic(request, {
    rules: options.deterministicRules,
  });

  if (deterministic) {
    results.push(deterministic);
    if (deterministic.confidence >= DETERMINISTIC_SKIP_LLM_THRESHOLD) {
      return results;
    }
  }

  if (options.llmEnabled) {
    // LLM classifier is not implemented in the scaffold.
  }

  if (results.length === 0) {
    results.push({
      intent: UNKNOWN_INTENT,
      confidence: 0.3,
      alternatives: [],
      classifier: 'deterministic:v1',
      reasoning: 'No deterministic classification',
    });
  }

  return results;
}
