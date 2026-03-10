/**
 * CrossExam API Service
 *
 * API client for the CrossExam shard backend.
 * Endpoints: /trees, /nodes, /impeachments, /generate
 */

const API_PREFIX = '/api/crossexam';

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
// Question Trees
// ============================================

export async function listTrees(
  witnessId?: string,
  projectId?: string
): Promise<{ count: number; trees: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (witnessId) params.set('witness_id', witnessId);
  if (projectId) params.set('project_id', projectId);

  const query = params.toString();
  return fetchAPI(`/trees${query ? `?${query}` : ''}`);
}

export async function getTreeNodes(
  treeId: string
): Promise<{ count: number; nodes: Record<string, unknown>[] }> {
  return fetchAPI(`/trees/${treeId}/nodes`);
}

export async function createTree(data: {
  witness_id: string;
  title: string;
  description?: string;
  project_id?: string;
  created_by?: string;
}): Promise<{ tree_id: string }> {
  return fetchAPI('/trees', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================
// Question Nodes
// ============================================

export async function createNode(data: {
  tree_id: string;
  parent_id?: string;
  question_text: string;
  expected_answer?: string;
  alternative_answer?: string;
  damage_potential?: number;
}): Promise<{ node_id: string }> {
  return fetchAPI('/nodes', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================
// Impeachments
// ============================================

export async function listImpeachments(
  witnessId?: string
): Promise<{ count: number; impeachments: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (witnessId) params.set('witness_id', witnessId);

  const query = params.toString();
  return fetchAPI(`/impeachments${query ? `?${query}` : ''}`);
}

export async function createImpeachment(data: {
  witness_id: string;
  title: string;
  conflict_description: string;
  statement_claim_id?: string;
  document_evidence_id?: string;
  steps?: Record<string, unknown>[];
}): Promise<{ impeachment_id: string }> {
  return fetchAPI('/impeachments', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ============================================
// AI Generation
// ============================================

export async function generateQuestionTree(
  witnessId: string,
  projectId: string
): Promise<{ status: string; witness_id: string; message: string }> {
  const params = new URLSearchParams({ witness_id: witnessId, project_id: projectId });
  return fetchAPI(`/generate/question-tree?${params}`, {
    method: 'POST',
  });
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
