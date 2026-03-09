/**
 * BurdenMap Types
 *
 * Type definitions matching the backend BurdenMap shard models.
 */

// Item status
export type ItemStatus = 'active' | 'archived' | 'deleted';

// Item in the BurdenMap shard
export interface BurdenMapItem {
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
export interface BurdenMapListItem {
  id: string;
  title: string;
  description: string;
  status: ItemStatus;
  created_at: string;
  updated_at: string;
}

// API response types
export interface BurdenMapListResponse {
  count: number;
  items: BurdenMapListItem[];
}

export const STATUS_OPTIONS: { value: ItemStatus; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'archived', label: 'Archived' },
  { value: 'deleted', label: 'Deleted' },
];
