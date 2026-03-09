/**
 * Playbook Types
 *
 * Type definitions matching the backend Playbook shard models.
 */

// Item status
export type ItemStatus = 'active' | 'archived' | 'deleted';

// Item in the Playbook shard
export interface PlaybookItem {
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
export interface PlaybookListItem {
  id: string;
  title: string;
  description: string;
  status: ItemStatus;
  created_at: string;
  updated_at: string;
}

// API response types
export interface PlaybookListResponse {
  count: number;
  items: PlaybookListItem[];
}

export const STATUS_OPTIONS: { value: ItemStatus; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'archived', label: 'Archived' },
  { value: 'deleted', label: 'Deleted' },
];
