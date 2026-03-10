/**
 * Rules API Service
 *
 * API client for the Procedural Rules Engine shard backend.
 */

import type { RulesItem, RulesListResponse, RuleCategory } from './types';

const API_PREFIX = '/api/rules';

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
// Rules (Items) Operations
// ============================================

export async function listItems(projectId?: string, status?: string): Promise<RulesListResponse> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  if (status) params.set('status', status);

  const query = params.toString();
  return fetchAPI<RulesListResponse>(`/items${query ? `?${query}` : ''}`);
}

export async function getItem(itemId: string): Promise<RulesItem> {
  return fetchAPI<RulesItem>(`/items/${itemId}`);
}

export async function createItem(data: {
  title: string;
  description?: string;
  project_id?: string;
  created_by?: string;
  metadata?: {
    rule_number?: string;
    category?: RuleCategory;
    source?: string;
    deadline_formula?: string;
    statutory_reference?: string;
  };
}): Promise<{ item_id: string; title: string; status: string }> {
  return fetchAPI('/items', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateItem(
  itemId: string,
  data: {
    title?: string;
    description?: string;
    status?: string;
    metadata?: Record<string, unknown>;
  }
): Promise<{ item_id: string; status: string }> {
  return fetchAPI(`/items/${itemId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteItem(itemId: string): Promise<{ status: string; item_id: string }> {
  return fetchAPI(`/items/${itemId}`, {
    method: 'DELETE',
  });
}

export async function getItemCount(): Promise<{ count: number }> {
  return fetchAPI('/items/count');
}
