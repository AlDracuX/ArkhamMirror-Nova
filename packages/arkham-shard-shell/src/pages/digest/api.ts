/**
 * Digest API Service
 *
 * API client for the Digest shard backend.
 * Endpoints: /briefings, /project/{id}/briefings, /project/{id}/changes
 */

const API_PREFIX = '/api/digest';

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
// Briefings
// ============================================

export async function generateBriefing(data: {
  project_id: string;
  type?: string;
  metadata?: Record<string, unknown>;
}): Promise<{ id: string }> {
  return fetchAPI('/briefings', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getBriefing(
  briefId: string
): Promise<Record<string, unknown>> {
  return fetchAPI(`/briefings/${briefId}`);
}

export async function listBriefings(
  projectId: string
): Promise<Record<string, unknown>[]> {
  return fetchAPI(`/project/${projectId}/briefings`);
}

// ============================================
// Change Log
// ============================================

export async function getChangelog(
  projectId: string,
  limit?: number
): Promise<Record<string, unknown>[]> {
  const params = new URLSearchParams();
  if (limit !== undefined) params.set('limit', String(limit));

  const query = params.toString();
  return fetchAPI(`/project/${projectId}/changes${query ? `?${query}` : ''}`);
}


export async function listItems(
  projectId?: string,
  status?: string
): Promise<{ count: number; items: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  if (status) params.set("status", status);
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
