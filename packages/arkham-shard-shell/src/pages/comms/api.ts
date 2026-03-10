/**
 * Comms API Service
 *
 * API client for the Comms (Communication Analysis) shard backend.
 * Endpoints: /threads, /messages, /participants, /gaps, /coordination-flags
 */

const API_PREFIX = '/api/comms';

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
// Threads
// ============================================

export async function listThreads(projectId?: string): Promise<Record<string, unknown>[]> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);

  const query = params.toString();
  return fetchAPI(`/threads${query ? `?${query}` : ''}`);
}

export async function createThread(data: {
  subject: string;
  description?: string;
  project_id?: string;
  created_by?: string;
  metadata?: Record<string, unknown>;
}): Promise<{ id: string; status: string }> {
  return fetchAPI('/threads', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================
// Messages
// ============================================

export async function listMessages(threadId?: string): Promise<Record<string, unknown>[]> {
  const params = new URLSearchParams();
  if (threadId) params.set('thread_id', threadId);

  const query = params.toString();
  return fetchAPI(`/messages${query ? `?${query}` : ''}`);
}

export async function createMessage(data: {
  thread_id: string;
  subject?: string;
  body_summary?: string;
  sent_at?: string;
  from_address?: string;
  to_addresses?: string[];
  cc_addresses?: string[];
  bcc_addresses?: string[];
  source_document_id?: string;
  metadata?: Record<string, unknown>;
}): Promise<{ id: string; status: string }> {
  return fetchAPI('/messages', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================
// Participants
// ============================================

export async function listParticipants(): Promise<Record<string, unknown>[]> {
  return fetchAPI('/participants');
}

// ============================================
// Gaps & Coordination Flags
// ============================================

export async function listGaps(threadId?: string): Promise<Record<string, unknown>[]> {
  const params = new URLSearchParams();
  if (threadId) params.set('thread_id', threadId);

  const query = params.toString();
  return fetchAPI(`/gaps${query ? `?${query}` : ''}`);
}

export async function listCoordinationFlags(threadId?: string): Promise<Record<string, unknown>[]> {
  const params = new URLSearchParams();
  if (threadId) params.set('thread_id', threadId);

  const query = params.toString();
  return fetchAPI(`/coordination-flags${query ? `?${query}` : ''}`);
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
