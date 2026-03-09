/**
 * AuditTrail Types
 *
 * Type definitions matching the backend AuditTrail shard models.
 */

// Item status
export type ItemStatus = 'active' | 'archived' | 'deleted';

// Item in the AuditTrail shard
export interface AuditTrailItem {
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

// List item (summary view)
export interface AuditTrailListItem {
  id: string;
  title: string;
  description: string;
  status: ItemStatus;
  created_at: string;
  updated_at: string;
}

// API response types
export interface AuditTrailListResponse {
  count: number;
  items: AuditTrailListItem[];
}

export const STATUS_OPTIONS: { value: ItemStatus; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'archived', label: 'Archived' },
  { value: 'deleted', label: 'Deleted' },
];
