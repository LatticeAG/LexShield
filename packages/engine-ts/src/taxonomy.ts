/** Built-in intent taxonomy severity ranks (SPEC Appendix B, frozen v0.1). */

export const BUILTIN_INTENT_SEVERITY: Readonly<Record<string, number>> = {
  'network.request.health': 5,
  'data.read.public': 10,
  'data.read.internal': 25,
  'comms.read.inbox': 35,
  'comms.send.slack': 40,
  'data.query.sql': 40,
  'data.write.record': 45,
  'comms.send.email': 50,
  'unknown.unclassified': 50,
  'code.write.repo': 50,
  'network.request.http': 55,
  'data.read.pii': 60,
  'infra.provision.resource': 60,
  'infra.mutate.resource': 65,
  'comms.send.external': 70,
  'data.delete.record': 75,
  'finance.charge.create': 80,
  'infra.delete.resource': 85,
  'identity.permission.grant': 85,
  'code.execute.shell': 88,
  'finance.transfer.create': 90,
  'identity.auth.impersonate': 90,
  'data.exfiltrate': 95,
  'security.secret_exposure': 98,
};

export const BUILTIN_TAXONOMY_VERSION = 'v0.1';

export const BUILTIN_INTENTS: readonly string[] = Object.freeze(
  Object.keys(BUILTIN_INTENT_SEVERITY).sort(),
);

const DEFAULT_UNKNOWN_SEVERITY = 50;
const CUSTOM_INTENT_DEFAULT_SEVERITY = 50;

export interface Taxonomy {
  version: string;
  intents: Record<string, number>;
}

export function getIntentSeverity(intent: string, taxonomy: Taxonomy = builtinTaxonomy()): number {
  if (intent in taxonomy.intents) {
    return taxonomy.intents[intent]!;
  }

  if (intent.startsWith('custom.')) {
    return CUSTOM_INTENT_DEFAULT_SEVERITY;
  }

  return DEFAULT_UNKNOWN_SEVERITY;
}

export function builtinTaxonomy(): Taxonomy {
  return {
    version: BUILTIN_TAXONOMY_VERSION,
    intents: { ...BUILTIN_INTENT_SEVERITY },
  };
}

export function mergeTaxonomy(customIntents: Record<string, number> = {}): Taxonomy {
  return {
    version: BUILTIN_TAXONOMY_VERSION,
    intents: {
      ...BUILTIN_INTENT_SEVERITY,
      ...customIntents,
    },
  };
}
