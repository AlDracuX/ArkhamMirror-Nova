/**
 * Oracle API Service
 *
 * API client for the Oracle (Legal Research) shard backend.
 * Endpoints: /research, /sessions, /authorities, /project
 */

const API_PREFIX = '/api/oracle';

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
// Research Sessions
// ============================================

export async function startResearch(data: {
  project_id: string;
  query: string;
  metadata?: Record<string, unknown>;
}): Promise<{ id: string }> {
  return fetchAPI('/research', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getSession(
  sessionId: string
): Promise<Record<string, unknown>> {
  return fetchAPI(`/sessions/${sessionId}`);
}

// ============================================
// Authorities
// ============================================

export async function getAuthority(
  authId: string
): Promise<Record<string, unknown>> {
  return fetchAPI(`/authorities/${authId}`);
}

export async function listAuthorities(
  projectId: string
): Promise<Record<string, unknown>[]> {
  return fetchAPI(`/project/${projectId}/authorities`);
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
