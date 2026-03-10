/**
 * Disclosure API Service
 *
 * API client for the Disclosure shard backend.
 * Endpoints: /requests, /responses, /gaps, /evasion, /compliance
 */

const API_PREFIX = '/api/disclosure';

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
// Disclosure Requests
// ============================================

export async function listRequests(
  respondentId?: string
): Promise<{ count: number; requests: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (respondentId) params.set('respondent_id', respondentId);

  const query = params.toString();
  return fetchAPI(`/requests${query ? `?${query}` : ''}`);
}

export async function createRequest(data: {
  respondent_id: string;
  request_text: string;
  deadline?: string;
}): Promise<{ request_id: string }> {
  return fetchAPI('/requests', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================
// Disclosure Responses
// ============================================

export async function listResponses(
  requestId?: string
): Promise<{ count: number; responses: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (requestId) params.set('request_id', requestId);

  const query = params.toString();
  return fetchAPI(`/responses${query ? `?${query}` : ''}`);
}

export async function createResponse(data: {
  request_id: string;
  response_text: string;
  document_ids?: string[];
  received_at?: string;
}): Promise<{ response_id: string }> {
  return fetchAPI('/responses', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================
// Disclosure Gaps
// ============================================

export async function listGaps(
  requestId?: string
): Promise<{ count: number; gaps: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (requestId) params.set('request_id', requestId);

  const query = params.toString();
  return fetchAPI(`/gaps${query ? `?${query}` : ''}`);
}

export async function createGap(data: {
  request_id: string;
  missing_items_description: string;
  status?: string;
}): Promise<{ gap_id: string }> {
  return fetchAPI('/gaps', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================
// Evasion Scores
// ============================================

export async function listEvasionScores(
  respondentId?: string
): Promise<{ count: number; scores: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (respondentId) params.set('respondent_id', respondentId);

  const query = params.toString();
  return fetchAPI(`/evasion${query ? `?${query}` : ''}`);
}

export async function createEvasionScore(data: {
  respondent_id: string;
  score: number;
  reason?: string;
}): Promise<{ score_id: string }> {
  return fetchAPI('/evasion', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================
// Compliance Dashboard
// ============================================

export async function getComplianceDashboard(): Promise<{
  respondents: Record<string, unknown>[];
}> {
  return fetchAPI('/compliance');
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
