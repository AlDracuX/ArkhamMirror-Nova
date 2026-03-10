/**
 * Bundle API Service
 *
 * API client for the Bundle shard backend.
 * Backend routes: /bundles CRUD, /bundles/{id}/compile, /bundles/{id}/versions,
 *                 /versions/{id}/pages, /versions/{id}/index
 */

const API_PREFIX = '/api/bundle';

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
// Bundles CRUD
// ============================================

export async function listBundles(
  projectId?: string,
  status?: string
): Promise<{ count: number; bundles: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  if (status) params.set('status', status);

  const query = params.toString();
  return fetchAPI(`/bundles${query ? `?${query}` : ''}`);
}

export async function getBundle(bundleId: string): Promise<Record<string, unknown>> {
  return fetchAPI(`/bundles/${bundleId}`);
}

export async function createBundle(data: {
  title: string;
  description?: string;
  project_id?: string;
  created_by?: string;
}): Promise<{ bundle_id: string; title: string; status: string }> {
  return fetchAPI('/bundles', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateBundle(
  bundleId: string,
  data: {
    title?: string;
    description?: string;
    status?: string;
  }
): Promise<{ bundle_id: string; status: string }> {
  return fetchAPI(`/bundles/${bundleId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteBundle(
  bundleId: string
): Promise<{ status: string; bundle_id: string }> {
  return fetchAPI(`/bundles/${bundleId}`, {
    method: 'DELETE',
  });
}

// ============================================
// Compilation
// ============================================

export async function compileBundle(
  bundleId: string,
  data: {
    document_ids: string[];
    document_overrides?: Record<string, unknown>;
    section_headers?: Record<string, string>;
    change_notes?: string;
    compiled_by?: string;
  }
): Promise<{
  status: string;
  bundle_id: string;
  version_id: string;
  version_number: number;
  total_pages: number;
  index: Record<string, unknown>;
}> {
  return fetchAPI(`/bundles/${bundleId}/compile`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================
// Versions
// ============================================

export async function listVersions(
  bundleId: string
): Promise<{ bundle_id: string; versions: Record<string, unknown>[] }> {
  return fetchAPI(`/bundles/${bundleId}/versions`);
}

export async function getVersionPages(
  versionId: string
): Promise<{ version_id: string; pages: Record<string, unknown>[] }> {
  return fetchAPI(`/versions/${versionId}/pages`);
}

export async function getVersionIndex(versionId: string): Promise<Record<string, unknown>> {
  return fetchAPI(`/versions/${versionId}/index`);
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
