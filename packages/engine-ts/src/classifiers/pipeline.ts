import { classifyDeterministic } from './deterministic.js';
import type { Classification, DeterministicRules, ToolCallRequest } from '../types.js';

const DETERMINISTIC_SKIP_LLM_THRESHOLD = 0.9;

export interface ClassifierPipelineOptions {
  deterministicRules?: DeterministicRules;
  llmEnabled?: boolean;
}

export async function runClassifierPipeline(
  request: ToolCallRequest,
  options: ClassifierPipelineOptions = {},
): Promise<Classification[]> {
  const deterministicRules = options.deterministicRules ?? {
    version: '1',
    tool_map: {},
    patterns: [],
  };

  const deterministic = classifyDeterministic(request, { rules: deterministicRules });
  const primary = deterministic[0];

  if (primary && primary.confidence >= DETERMINISTIC_SKIP_LLM_THRESHOLD) {
    return deterministic;
  }

  if (options.llmEnabled) {
    // LLM classifier is not implemented in the scaffold.
  }

  return deterministic;
}
