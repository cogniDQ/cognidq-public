/** Resolution types matching backend F102 ResolveResponse schema. */

export interface SignalBreakdown {
  signal_name: string;
  score: number;
  evidence: string;
}

export interface ResolutionCandidate {
  asset_id: string;
  column_name: string;
  dataset_name?: string;
  dataset_id?: string;
  data_type?: string;
  overall_score: number;
  confidence_band: 'high' | 'medium' | 'low';
  signal_breakdown: SignalBreakdown[];
  evidence_summary: string[];
}

export interface EntityResolution {
  raw_text: string;
  candidates: ResolutionCandidate[];
  best_candidate: ResolutionCandidate | null;
  requires_disambiguation: boolean;
}

export interface ResolveRequest {
  parsed_rule: Record<string, unknown>;
  dataset_context?: string;
  domain_context?: string;
  selected_candidates?: Record<string, string>;
}

export interface GlossaryMatch {
  term_id: string;
  business_name: string;
  technical_name?: string;
  domain?: string;
  definition?: string;
  match_score: number;
  match_type: 'exact' | 'synonym' | 'fuzzy';
  matched_on: string;
}

export interface ResolveResponse {
  resolved_rule: Record<string, unknown>;
  subject_resolution: EntityResolution;
  object_resolution: EntityResolution | null;
  overall_confidence: number;
  requires_disambiguation: boolean;
  resolution_evidence: Record<string, unknown>;
  glossary_matches: GlossaryMatch[];
}
