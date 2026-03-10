/**
 * Comparator API Service
 *
 * API client for the Comparator (Discrimination Analysis) shard backend.
 * Endpoints: /comparators, /incidents, /treatments, /divergences, /matrix, /analyze
 */

const API_PREFIX = '/api/comparator';

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
// Comparators CRUD
// ============================================

export async function listComparators(
  tenantId?: string
): Promise<{ count: number; comparators: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (tenantId) params.set('tenant_id', tenantId);

  const query = params.toString();
  return fetchAPI(`/comparators${query ? `?${query}` : ''}`);
}

export async function getComparator(comparatorId: string): Promise<Record<string, unknown>> {
  return fetchAPI(`/comparators/${comparatorId}`);
}

export async function createComparator(data: {
  name: string;
  characteristic?: string;
}): Promise<{ comparator_id: string; name: string }> {
  return fetchAPI('/comparators', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateComparator(
  comparatorId: string,
  data: { name?: string; characteristic?: string }
): Promise<{ comparator_id: string; status: string }> {
  return fetchAPI(`/comparators/${comparatorId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteComparator(
  comparatorId: string
): Promise<{ status: string; comparator_id: string }> {
  return fetchAPI(`/comparators/${comparatorId}`, {
    method: 'DELETE',
  });
}

// ============================================
// Incidents CRUD
// ============================================

export async function listIncidents(
  projectId?: string,
  tenantId?: string
): Promise<{ count: number; incidents: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  if (tenantId) params.set('tenant_id', tenantId);

  const query = params.toString();
  return fetchAPI(`/incidents${query ? `?${query}` : ''}`);
}

export async function getIncident(incidentId: string): Promise<Record<string, unknown>> {
  return fetchAPI(`/incidents/${incidentId}`);
}

export async function createIncident(data: {
  description: string;
  date?: string;
  project_id?: string;
}): Promise<{ incident_id: string; description: string }> {
  return fetchAPI('/incidents', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateIncident(
  incidentId: string,
  data: { description?: string; date?: string; project_id?: string }
): Promise<{ incident_id: string; status: string }> {
  return fetchAPI(`/incidents/${incidentId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteIncident(
  incidentId: string
): Promise<{ status: string; incident_id: string }> {
  return fetchAPI(`/incidents/${incidentId}`, {
    method: 'DELETE',
  });
}

// ============================================
// Treatments CRUD
// ============================================

export async function listTreatments(
  incidentId?: string,
  subjectId?: string
): Promise<{ count: number; treatments: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (incidentId) params.set('incident_id', incidentId);
  if (subjectId) params.set('subject_id', subjectId);

  const query = params.toString();
  return fetchAPI(`/treatments${query ? `?${query}` : ''}`);
}

export async function getTreatment(treatmentId: string): Promise<Record<string, unknown>> {
  return fetchAPI(`/treatments/${treatmentId}`);
}

export async function createTreatment(data: {
  incident_id: string;
  subject_id: string;
  treatment_description: string;
  outcome?: string;
  evidence_ids?: string[];
}): Promise<{ treatment_id: string; incident_id: string; subject_id: string }> {
  return fetchAPI('/treatments', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateTreatment(
  treatmentId: string,
  data: {
    treatment_description?: string;
    outcome?: string;
    evidence_ids?: string[];
  }
): Promise<{ treatment_id: string; status: string }> {
  return fetchAPI(`/treatments/${treatmentId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteTreatment(
  treatmentId: string
): Promise<{ status: string; treatment_id: string }> {
  return fetchAPI(`/treatments/${treatmentId}`, {
    method: 'DELETE',
  });
}

// ============================================
// Divergences CRUD
// ============================================

export async function listDivergences(
  incidentId?: string,
  minScore?: number
): Promise<{ count: number; divergences: Record<string, unknown>[] }> {
  const params = new URLSearchParams();
  if (incidentId) params.set('incident_id', incidentId);
  if (minScore !== undefined) params.set('min_score', String(minScore));

  const query = params.toString();
  return fetchAPI(`/divergences${query ? `?${query}` : ''}`);
}

export async function getDivergence(divergenceId: string): Promise<Record<string, unknown>> {
  return fetchAPI(`/divergences/${divergenceId}`);
}

export async function createDivergence(data: {
  incident_id: string;
  description: string;
  significance_score?: number;
}): Promise<{ divergence_id: string; incident_id: string }> {
  return fetchAPI('/divergences', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateDivergence(
  divergenceId: string,
  data: { description?: string; significance_score?: number }
): Promise<{ divergence_id: string; status: string }> {
  return fetchAPI(`/divergences/${divergenceId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteDivergence(
  divergenceId: string
): Promise<{ status: string; divergence_id: string }> {
  return fetchAPI(`/divergences/${divergenceId}`, {
    method: 'DELETE',
  });
}

// ============================================
// Comparison Matrix
// ============================================

export async function getComparisonMatrix(
  projectId?: string,
  tenantId?: string
): Promise<{
  incidents: Record<string, unknown>[];
  comparators: Record<string, unknown>[];
  matrix: Record<string, Record<string, unknown>>;
  divergences: Record<string, Record<string, unknown>[]>;
}> {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  if (tenantId) params.set('tenant_id', tenantId);

  const query = params.toString();
  return fetchAPI(`/matrix${query ? `?${query}` : ''}`);
}

// ============================================
// Advanced Analysis
// ============================================

export async function detectParallelSituations(
  projectId: string
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({ project_id: projectId });
  return fetchAPI(`/analyze/parallel-situations?${params}`, {
    method: 'POST',
  });
}

export async function getCharacteristicLinkage(
  projectId: string
): Promise<{ project_id: string; linkage_data: Record<string, unknown>[] }> {
  const params = new URLSearchParams({ project_id: projectId });
  return fetchAPI(`/analyze/linkage?${params}`);
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
