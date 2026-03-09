/**
 * Redline API Service
 *
 * API client for the Redline shard backend.
 * Backend routes: POST /comparisons, GET /comparisons/{id}, GET /project/{id}/chains
 */

const API_PREFIX = '/api/redline';

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
// Comparisons
// ============================================

export async function createComparison(data: {
  project_id: string;
  base_document_id: string;
  target_document_id: string;
  metadata?: Record<string, unknown>;
}): Promise<{ id: string }> {
  return fetchAPI('/comparisons', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getComparison(compId: string): Promise<Record<string, unknown>> {
  return fetchAPI(`/comparisons/${compId}`);
}

// ============================================
// Version Chains
// ============================================

export async function listChains(projectId: string): Promise<Record<string, unknown>[]> {
  return fetchAPI(`/project/${projectId}/chains`);
}


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
  return fetchAPI(`/items${query ? `?${query}` : ""}`);
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
  return fetchAPI("/items", {
    method: "POST",
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
