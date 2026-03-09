/**
 * RespondentIntel API Service
 *
 * API client for the RespondentIntel shard backend.
 * Endpoints: /profiles
 */

const API_PREFIX = '/api/respondent-intel';

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
// Profiles
// ============================================

export async function listProfiles(): Promise<Record<string, unknown>[]> {
  return fetchAPI('/profiles');
}

export async function getProfile(
  profileId: string
): Promise<Record<string, unknown>> {
  return fetchAPI(`/profiles/${profileId}`);
}

export async function createProfile(data: {
  name: string;
  type: string;
  metadata?: Record<string, unknown>;
}): Promise<{ id: string }> {
  return fetchAPI('/profiles', {
    method: 'POST',
    body: JSON.stringify(data),
  });
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
