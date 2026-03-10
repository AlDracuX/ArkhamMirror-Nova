/**
 * BurdenMap API Service
 *
 * API client for the BurdenMap (Burden of Proof) shard backend.
 * Backend routes: /elements, /dashboard, /weights
 */

const API_PREFIX = '/api/burden-map';

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
// Claim Elements
// ============================================

export async function listElements(
  projectId?: string
): Promise<{ count: number; elements: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);

  const query = params.toString();
  return fetchAPI(`/elements${query ? `?${query}` : ''}`);
}

export async function createElement(data: {
  title: string;
  claim_type: string;
  statutory_reference?: string;
  description?: string;
  burden_holder?: string;
  required?: boolean;
  theory_id?: string;
  linked_claim_id?: string;
  project_id?: string;
}): Promise<{ element_id: string }> {
  return fetchAPI('/elements', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================
// Burden Dashboard (Traffic Light Matrix)
// ============================================

export async function getBurdenDashboard(
  projectId?: string
): Promise<{ elements: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);

  const query = params.toString();
  return fetchAPI(`/dashboard${query ? `?${query}` : ''}`);
}

// ============================================
// Evidence Weights
// ============================================

export async function addEvidenceWeight(data: {
  element_id: string;
  weight: string;
  source_type?: string;
  source_id: string;
  source_title: string;
  excerpt?: string;
  supports_burden_holder?: boolean;
  analyst_notes?: string;
}): Promise<{ weight_id: string; status: string }> {
  return fetchAPI('/weights', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function listItems(
  projectId?: string,
  status?: string
): Promise<{ count: number; items: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  if (status) params.set('status', status);
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
