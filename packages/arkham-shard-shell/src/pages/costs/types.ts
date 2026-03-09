/**
 * Costs Types
 *
 * Type definitions for the Costs & Wasted Costs Tracker shard.
 * Tracks time, expenses, and respondent conduct for costs applications.
 */

// Item status (generic backend)
export type ItemStatus = 'active' | 'archived' | 'deleted';

// Entry type for costs items
export type CostEntryType = 'time' | 'expense' | 'conduct' | 'application';

// Conduct category (for Rule 76 threshold tracking)
export type ConductCategory =
  | 'delay'
  | 'evasion'
  | 'vexatious'
  | 'unreasonable'
  | 'non_compliance'
  | 'deception';

// Application status
export type ApplicationStatus = 'draft' | 'filed' | 'granted' | 'refused' | 'pending';

// A costs item from the backend
export interface CostsItem {
  id: string;
  tenant_id: string | null;
  title: string;
  description: string;
  project_id: string | null;
  status: ItemStatus;
  metadata: {
    entry_type?: CostEntryType;
    // Time entry fields
    hours?: number;
    hourly_rate?: number;
    activity_date?: string;
    // Expense fields
    amount?: number;
    currency?: string;
    receipt_ref?: string;
    // Conduct fields
    conduct_category?: ConductCategory;
    respondent?: string;
    evidence_date?: string;
    evidence_refs?: string[];
    rule_breached?: string;
    // Application fields
    application_status?: ApplicationStatus;
    total_claimed?: number;
    conduct_instances?: string[];
  };
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

// List item (summary view)
export interface CostsListItem {
  id: string;
  title: string;
  description: string;
  status: ItemStatus;
  created_at: string;
  updated_at: string;
  metadata?: {
    entry_type?: CostEntryType;
    hours?: number;
    amount?: number;
    conduct_category?: ConductCategory;
    respondent?: string;
    application_status?: ApplicationStatus;
  };
}

// API response types
export interface CostsListResponse {
  count: number;
  items: CostsListItem[];
}

// Summary stats
export interface CostsSummary {
  total_time_hours: number;
  total_time_value: number;
  total_expenses: number;
  total_claimed: number;
  conduct_instances: number;
  applications_count: number;
}

export const STATUS_OPTIONS: { value: ItemStatus; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'archived', label: 'Archived' },
  { value: 'deleted', label: 'Deleted' },
];

export const ENTRY_TYPE_OPTIONS: { value: CostEntryType; label: string; color: string }[] = [
  { value: 'time', label: 'Time Entry', color: '#2563eb' },
  { value: 'expense', label: 'Expense', color: '#059669' },
  { value: 'conduct', label: 'Conduct Log', color: '#dc2626' },
  { value: 'application', label: 'Application', color: '#7c3aed' },
];

export const CONDUCT_OPTIONS: { value: ConductCategory; label: string; color: string }[] = [
  { value: 'delay', label: 'Delay', color: '#d97706' },
  { value: 'evasion', label: 'Evasion', color: '#ea580c' },
  { value: 'vexatious', label: 'Vexatious', color: '#dc2626' },
  { value: 'unreasonable', label: 'Unreasonable', color: '#b91c1c' },
  { value: 'non_compliance', label: 'Non-compliance', color: '#7c3aed' },
  { value: 'deception', label: 'Deception', color: '#991b1b' },
];

export const APPLICATION_STATUS_OPTIONS: { value: ApplicationStatus; label: string; color: string }[] = [
  { value: 'draft', label: 'Draft', color: '#6b7280' },
  { value: 'filed', label: 'Filed', color: '#2563eb' },
  { value: 'pending', label: 'Pending', color: '#d97706' },
  { value: 'granted', label: 'Granted', color: '#16a34a' },
  { value: 'refused', label: 'Refused', color: '#dc2626' },
];
