/**
 * Strategist API Service
 *
 * API client for the Strategist shard backend.
 * Backend routes: POST /predictions, GET /predictions/{id},
 *                 GET /project/{id}/reports, GET /project/{id}/tactical-models
 */

const API_PREFIX = '/api/strategist';

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
// Predictions
// ============================================

export async function createPrediction(data: {
  project_id: string;
  claim_id?: string;
  respondent_id?: string;
  metadata?: Record<string, unknown>;
}): Promise<{ id: string }> {
  return fetchAPI('/predictions', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getPrediction(predId: string): Promise<Record<string, unknown>> {
  return fetchAPI(`/predictions/${predId}`);
}

// ============================================
// Red Team Reports
// ============================================

export async function listReports(projectId: string): Promise<Record<string, unknown>[]> {
  return fetchAPI(`/project/${projectId}/reports`);
}

// ============================================
// Tactical Models
// ============================================

export async function listTacticalModels(projectId: string): Promise<Record<string, unknown>[]> {
  return fetchAPI(`/project/${projectId}/tactical-models`);
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
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteItem(itemId: string): Promise<{ status: string }> {
  return fetchAPI(`/items/${itemId}`, { method: 'DELETE' });
}
