/**
 * AuditTrail API Service
 *
 * API client for the AuditTrail shard backend.
 * Backend routes: /actions, /summary, /sessions, /exports
 */

const API_PREFIX = '/api/audit-trail';

// Generic fetch wrapper with error handling
async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_PREFIX}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || error.message || `HTTP ${response.status}`);
  }

  return response.json();
}

// ============================================
// Actions (immutable audit log)
// ============================================

export async function listActions(filters?: {
  user_id?: string;
  shard?: string;
  action_type?: string;
  entity_id?: string;
  limit?: number;
}): Promise<{ count: number; actions: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (filters?.user_id) params.set('user_id', filters.user_id);
  if (filters?.shard) params.set('shard', filters.shard);
  if (filters?.action_type) params.set('action_type', filters.action_type);
  if (filters?.entity_id) params.set('entity_id', filters.entity_id);
  if (filters?.limit) params.set('limit', String(filters.limit));

  const query = params.toString();
  return fetchAPI(`/actions${query ? `?${query}` : ''}`);
}

// ============================================
// Summary
// ============================================

export async function getAuditSummary(): Promise<{
  total_actions: number;
  shards: Record<string, number>;
}> {
  return fetchAPI('/summary');
}

// ============================================
// Sessions
// ============================================

export async function listSessions(
  limit?: number
): Promise<{ count: number; sessions: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (limit) params.set('limit', String(limit));

  const query = params.toString();
  return fetchAPI(`/sessions${query ? `?${query}` : ''}`);
}

// ============================================
// Exports
// ============================================

export async function listExports(
  limit?: number
): Promise<{ count: number; exports: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (limit) params.set('limit', String(limit));

  const query = params.toString();
  return fetchAPI(`/exports${query ? `?${query}` : ''}`);
}

export async function recordExport(data: {
  user_id?: string;
  export_format: string;
  filters_applied?: Record<string, unknown>;
  row_count?: number;
}): Promise<{ export_id: string; status: string }> {
  return fetchAPI('/exports', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================
// Generic CRUD stubs (used by page components)
// ============================================

export async function listItems(
  filters?: Record<string, unknown>
): Promise<{ count: number; items: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (filters) {
    Object.entries(filters).forEach(([k, v]) => {
      if (v != null) params.set(k, String(v));
    });
  }
  const query = params.toString();
  return fetchAPI(`/items${query ? `?${query}` : ''}`);
}

export async function getItem(itemId: string): Promise<Record<string, unknown>> {
  return fetchAPI(`/items/${itemId}`);
}

export async function createItem(data: {
  title: string;
  description?: string;
  project_id?: string;
  metadata?: Record<string, unknown>;
  created_by?: string;
}): Promise<{ id: string; status: string }> {
  return fetchAPI('/items', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}


export async function updateItem(
  itemId: string,
  data: Record<string, unknown>
): Promise<{ id: string; status: string }> {
  return fetchAPI(`/items/${itemId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteItem(itemId: string): Promise<{ status: string }> {
  return fetchAPI(`/items/${itemId}`, { method: "DELETE" });
}
