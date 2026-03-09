/**
 * Skeleton Types
 *
 * Type definitions for the Legal Argument Builder shard.
 * Structures skeleton arguments and legal submissions in ET-compliant format.
 */

// Argument tree status
export type ArgumentStatus = 'draft' | 'structured' | 'final';

// Item status (generic backend)
export type ItemStatus = 'active' | 'archived' | 'deleted';

// Authority binding level
export type BindingLevel = 'binding' | 'persuasive' | 'obiter';

// Submission type
export type SubmissionType = 'full' | 'skeleton' | 'oral_notes';

// An authority (case law reference)
export interface Authority {
  case_name: string;
  citation: string;
  court: string;
  ratio: string;
  binding_level: BindingLevel;
  year?: number;
}

// An element in the argument tree
export interface ArgumentElement {
  id: string;
  type: 'claim' | 'legal_test' | 'evidence' | 'authority';
  label: string;
  detail: string;
  children: ArgumentElement[];
  bundle_refs?: string[];
}

// Skeleton item from the backend
export interface SkeletonItem {
  id: string;
  tenant_id: string | null;
  title: string;
  description: string;
  project_id: string | null;
  status: ItemStatus;
  metadata: {
    argument_status?: ArgumentStatus;
    submission_type?: SubmissionType;
    claim_reference?: string;
    authorities?: Authority[];
    argument_tree?: ArgumentElement[];
    bundle_page_refs?: Record<string, string>;
    paragraph_count?: number;
  };
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

// List item (summary view)
export interface SkeletonListItem {
  id: string;
  title: string;
  description: string;
  status: ItemStatus;
  created_at: string;
  updated_at: string;
  metadata?: {
    argument_status?: ArgumentStatus;
    submission_type?: SubmissionType;
    claim_reference?: string;
    paragraph_count?: number;
    authority_count?: number;
  };
}

// API response types
export interface SkeletonListResponse {
  count: number;
  items: SkeletonListItem[];
}

export const STATUS_OPTIONS: { value: ItemStatus; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'archived', label: 'Archived' },
  { value: 'deleted', label: 'Deleted' },
];

export const ARGUMENT_STATUS_OPTIONS: { value: ArgumentStatus; label: string; color: string }[] = [
  { value: 'draft', label: 'Draft', color: '#6b7280' },
  { value: 'structured', label: 'Structured', color: '#d97706' },
  { value: 'final', label: 'Final', color: '#16a34a' },
];

export const SUBMISSION_TYPE_OPTIONS: { value: SubmissionType; label: string }[] = [
  { value: 'full', label: 'Full Submission' },
  { value: 'skeleton', label: 'Skeleton Argument' },
  { value: 'oral_notes', label: 'Oral Hearing Notes' },
];

export const BINDING_LEVEL_OPTIONS: { value: BindingLevel; label: string; color: string }[] = [
  { value: 'binding', label: 'Binding', color: '#dc2626' },
  { value: 'persuasive', label: 'Persuasive', color: '#2563eb' },
  { value: 'obiter', label: 'Obiter', color: '#6b7280' },
];
