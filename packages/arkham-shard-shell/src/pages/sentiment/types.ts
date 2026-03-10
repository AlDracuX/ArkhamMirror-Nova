/**
 * Sentiment Types
 *
 * Type definitions for the Sentiment & Tone Analyzer shard.
 * LLM-powered analysis of tone, sentiment, and language patterns.
 */

// Item status (generic backend fallback)
export type ItemStatus = 'active' | 'archived' | 'deleted';

// Sentiment direction
export type SentimentDirection = 'hostile' | 'negative' | 'neutral' | 'positive' | 'supportive';

// Tone category
export type ToneCategory =
  | 'hostility'
  | 'gaslighting'
  | 'passive_aggressive'
  | 'dismissive'
  | 'professional'
  | 'supportive'
  | 'threatening'
  | 'patronising';

// Pattern type
export type PatternType =
  | 'escalation'
  | 'gaslighting'
  | 'tone_shift'
  | 'discriminatory_language'
  | 'comparator_divergence';

// A sentiment analysis record
export interface SentimentAnalysis {
  id: string;
  tenant_id: string | null;
  document_id: string | null;
  thread_id: string | null;
  project_id: string;
  summary: string;
  overall_sentiment: number;
  created_at: string;
  metadata: Record<string, unknown>;
  tone_scores?: ToneScore[];
}

// A tone score within an analysis
export interface ToneScore {
  id: string;
  analysis_id: string;
  category: ToneCategory;
  score: number;
  reasoning: string;
  evidence_segments: string[];
}

// A detected pattern
export interface SentimentPattern {
  id: string;
  project_id: string;
  type: PatternType;
  description: string;
  significance_score: number;
  analysis_ids: string[];
  metadata: Record<string, unknown>;
}

// A comparator divergence finding
export interface ComparatorDiff {
  id: string;
  project_id: string;
  claimant_analysis_id: string;
  comparator_analysis_id: string;
  divergence_score: number;
  description: string;
  findings: string[];
}

// Generic item for backward compat with /items endpoint
export interface SentimentItem {
  id: string;
  tenant_id: string | null;
  title: string;
  description: string;
  project_id: string | null;
  status: ItemStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

export interface SentimentListItem {
  id: string;
  title: string;
  description: string;
  status: ItemStatus;
  created_at: string;
  updated_at: string;
}

export interface SentimentListResponse {
  count: number;
  items: SentimentListItem[];
}

export const TONE_CATEGORY_OPTIONS: { value: ToneCategory; label: string; color: string }[] = [
  { value: 'hostility', label: 'Hostility', color: '#dc2626' },
  { value: 'gaslighting', label: 'Gaslighting', color: '#991b1b' },
  { value: 'passive_aggressive', label: 'Passive-Aggressive', color: '#ea580c' },
  { value: 'dismissive', label: 'Dismissive', color: '#d97706' },
  { value: 'threatening', label: 'Threatening', color: '#b91c1c' },
  { value: 'patronising', label: 'Patronising', color: '#c2410c' },
  { value: 'professional', label: 'Professional', color: '#2563eb' },
  { value: 'supportive', label: 'Supportive', color: '#16a34a' },
];

export const PATTERN_TYPE_OPTIONS: { value: PatternType; label: string; color: string }[] = [
  { value: 'escalation', label: 'Hostility Escalation', color: '#dc2626' },
  { value: 'gaslighting', label: 'Gaslighting Pattern', color: '#991b1b' },
  { value: 'tone_shift', label: 'Tone Shift', color: '#d97706' },
  { value: 'discriminatory_language', label: 'Discriminatory Language', color: '#7c3aed' },
  { value: 'comparator_divergence', label: 'Comparator Divergence', color: '#0891b2' },
];

export const SENTIMENT_DIRECTION_OPTIONS: {
  value: SentimentDirection;
  label: string;
  color: string;
}[] = [
  { value: 'hostile', label: 'Hostile', color: '#dc2626' },
  { value: 'negative', label: 'Negative', color: '#ea580c' },
  { value: 'neutral', label: 'Neutral', color: '#6b7280' },
  { value: 'positive', label: 'Positive', color: '#2563eb' },
  { value: 'supportive', label: 'Supportive', color: '#16a34a' },
];
