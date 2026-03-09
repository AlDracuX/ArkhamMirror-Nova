/**
 * Rules Types
 *
 * Type definitions for the Procedural Rules Engine shard.
 * Encodes Employment Tribunal Rules of Procedure, auto-calculates deadlines,
 * validates compliance, and detects respondent breaches.
 */

// Item status (generic backend)
export type ItemStatus = 'active' | 'archived' | 'deleted';

// Rule category
export type RuleCategory =
  | 'procedure'
  | 'disclosure'
  | 'case_management'
  | 'hearings'
  | 'costs'
  | 'appeals'
  | 'general';

// Breach severity
export type BreachSeverity = 'minor' | 'moderate' | 'serious' | 'critical';

// Compliance check result
export type ComplianceResult = 'pass' | 'fail' | 'warning' | 'not_applicable';

// A procedural rule
export interface RulesItem {
  id: string;
  tenant_id: string | null;
  title: string;
  description: string;
  project_id: string | null;
  status: ItemStatus;
  metadata: {
    rule_number?: string;
    category?: RuleCategory;
    source?: string;
    deadline_formula?: string;
    statutory_reference?: string;
    notes?: string;
    related_rules?: string[];
  };
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

// List item (summary view)
export interface RulesListItem {
  id: string;
  title: string;
  description: string;
  status: ItemStatus;
  created_at: string;
  updated_at: string;
  metadata?: {
    rule_number?: string;
    category?: RuleCategory;
    source?: string;
    statutory_reference?: string;
  };
}

// A deadline calculation entry
export interface DeadlineCalculation {
  id: string;
  rule_id: string;
  rule_title: string;
  trigger_event: string;
  trigger_date: string;
  calculated_deadline: string;
  days_remaining: number | null;
  status: 'pending' | 'met' | 'breached';
}

// A breach record
export interface BreachRecord {
  id: string;
  rule_id: string;
  rule_title: string;
  respondent: string;
  breach_date: string;
  severity: BreachSeverity;
  description: string;
  evidence_refs: string[];
  application_drafted: boolean;
}

// A compliance check
export interface ComplianceCheck {
  id: string;
  document_id: string;
  document_title: string;
  rule_id: string;
  rule_title: string;
  result: ComplianceResult;
  findings: string[];
  checked_at: string;
}

// API response types
export interface RulesListResponse {
  count: number;
  items: RulesListItem[];
}

export const STATUS_OPTIONS: { value: ItemStatus; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'archived', label: 'Archived' },
  { value: 'deleted', label: 'Deleted' },
];

export const CATEGORY_OPTIONS: { value: RuleCategory; label: string; color: string }[] = [
  { value: 'procedure', label: 'Procedure', color: '#2563eb' },
  { value: 'disclosure', label: 'Disclosure', color: '#7c3aed' },
  { value: 'case_management', label: 'Case Management', color: '#0891b2' },
  { value: 'hearings', label: 'Hearings', color: '#dc2626' },
  { value: 'costs', label: 'Costs', color: '#d97706' },
  { value: 'appeals', label: 'Appeals', color: '#059669' },
  { value: 'general', label: 'General', color: '#6b7280' },
];

export const SEVERITY_OPTIONS: { value: BreachSeverity; label: string; color: string }[] = [
  { value: 'minor', label: 'Minor', color: '#6b7280' },
  { value: 'moderate', label: 'Moderate', color: '#d97706' },
  { value: 'serious', label: 'Serious', color: '#ea580c' },
  { value: 'critical', label: 'Critical', color: '#dc2626' },
];
