/**
 * Chain API Service
 *
 * API client for the Chain of Custody shard backend.
 * Endpoints: /events, /integrity-check, /reports
 */

const API_PREFIX = '/api/chain';

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
// Custody Events
// ============================================

export async function logCustodyEvent(data: {
  document_id: string;
  action: string;
  actor: string;
  location: string;
  previous_event_id?: string;
  notes?: string;
}): Promise<{ status: string; event_id: string }> {
  return fetchAPI('/events', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getDocumentHistory(
  documentId: string
): Promise<{ document_id: string; history: Record<string, unknown>[] }> {
  return fetchAPI(`/events/${documentId}`);
}

// ============================================
// Integrity Verification
// ============================================

export async function verifyDocumentIntegrity(documentId: string): Promise<{
  document_id: string;
  valid: boolean;
  stored_hash: string;
  current_hash: string;
}> {
  return fetchAPI(`/integrity-check/${documentId}`);
}

// ============================================
// Provenance Reports
// ============================================

export async function generateProvenanceReport(
  documentId: string
): Promise<{ report_id: string; report: Record<string, unknown> }> {
  return fetchAPI(`/reports/${documentId}`, {
    method: 'POST',
  });
}

export async function listReports(
  documentId: string
): Promise<{ document_id: string; reports: Record<string, unknown>[] }> {
  return fetchAPI(`/reports/${documentId}`);
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
