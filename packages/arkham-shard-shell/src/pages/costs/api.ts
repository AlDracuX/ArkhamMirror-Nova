/**
 * Costs API Service
 *
 * API client for the Costs & Wasted Costs Tracker shard backend.
 * Endpoints: /time-entries, /expenses, /conduct-log, /applications
 */

const API_PREFIX = '/api/costs';

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
// Time Entries
// ============================================

export async function listTimeEntries(projectId?: string): Promise<Record<string, unknown>[]> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);

  const query = params.toString();
  return fetchAPI(`/time-entries${query ? `?${query}` : ''}`);
}

export async function createTimeEntry(data: {
  activity: string;
  duration_minutes: number;
  activity_date: string;
  project_id?: string;
  hourly_rate?: number;
  notes?: string;
}): Promise<{ id: string; status: string }> {
  return fetchAPI('/time-entries', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function listExpenses(projectId?: string): Promise<Record<string, unknown>[]> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);

  const query = params.toString();
  return fetchAPI(`/expenses${query ? `?${query}` : ''}`);
}

export async function createExpense(data: {
  description: string;
  amount: number;
  expense_date: string;
  currency?: string;
  receipt_document_id?: string;
  project_id?: string;
}): Promise<{ id: string; status: string }> {
  return fetchAPI('/expenses', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function listConductLog(projectId?: string): Promise<Record<string, unknown>[]> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);

  const query = params.toString();
  return fetchAPI(`/conduct-log${query ? `?${query}` : ''}`);
}

export async function createConductLog(data: {
  party_name: string;
  conduct_type: string;
  description?: string;
  occurred_at: string;
  supporting_evidence?: string[];
  significance?: string;
  legal_reference?: string;
  project_id?: string;
}): Promise<{ id: string; status: string }> {
  return fetchAPI('/conduct-log', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function listApplications(projectId?: string): Promise<Record<string, unknown>[]> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);

  const query = params.toString();
  return fetchAPI(`/applications${query ? `?${query}` : ''}`);
}
