/**
 * Sentiment API Service
 *
 * API client for the Sentiment & Tone Analyzer shard backend.
 * Uses real backend endpoints: /analyses, /project/{id}/patterns, /project/{id}/comparator-diffs
 * Also supports generic /items endpoint for backward compatibility.
 */

import type {
  SentimentAnalysis,
  SentimentPattern,
  ComparatorDiff,
  SentimentItem,
  SentimentListResponse,
} from './types';

const API_PREFIX = '/api/sentiment';

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
// Analysis Operations (primary domain endpoints)
// ============================================

export async function createAnalysis(data: {
  document_id?: string;
  thread_id?: string;
  project_id: string;
  metadata?: Record<string, unknown>;
}): Promise<{ id: string }> {
  return fetchAPI('/analyses', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getAnalysis(analysisId: string): Promise<SentimentAnalysis> {
  return fetchAPI<SentimentAnalysis>(`/analyses/${analysisId}`);
}

// ============================================
// Project-scoped queries
// ============================================

export async function listPatterns(projectId: string): Promise<SentimentPattern[]> {
  return fetchAPI<SentimentPattern[]>(`/project/${projectId}/patterns`);
}

export async function listComparatorDiffs(projectId: string): Promise<ComparatorDiff[]> {
  return fetchAPI<ComparatorDiff[]>(`/project/${projectId}/comparator-diffs`);
}

// ============================================
// Generic Item Operations (fallback for items endpoint)
// ============================================

export async function listItems(
  projectId?: string,
  status?: string
): Promise<SentimentListResponse> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  if (status) params.set('status', status);

  const query = params.toString();
  return fetchAPI<SentimentListResponse>(`/items${query ? `?${query}` : ''}`);
}

export async function getItem(itemId: string): Promise<SentimentItem> {
  return fetchAPI<SentimentItem>(`/items/${itemId}`);
}

export async function createItem(data: {
  title: string;
  description?: string;
  project_id?: string;
  created_by?: string;
}): Promise<{ item_id: string; title: string; status: string }> {
  return fetchAPI('/items', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateItem(
  itemId: string,
  data: {
    title?: string;
    description?: string;
    status?: string;
  }
): Promise<{ item_id: string; status: string }> {
  return fetchAPI(`/items/${itemId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteItem(itemId: string): Promise<{ status: string; item_id: string }> {
  return fetchAPI(`/items/${itemId}`, {
    method: 'DELETE',
  });
}
