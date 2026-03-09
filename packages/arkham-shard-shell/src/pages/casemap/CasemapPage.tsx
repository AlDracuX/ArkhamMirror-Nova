import React, { useState, useEffect, useCallback } from 'react';
import { Map, Scale, Plus, BarChart3, Grid3X3, ChevronRight } from 'lucide-react';

interface Theory {
  id: string;
  title: string;
  claim_type: string;
  statutory_basis: string;
  status: string;
  overall_strength: number;
  respondent_ids: string[];
  created_at: string;
}

const CLAIM_TYPE_LABELS: Record<string, string> = {
  unfair_dismissal: 'Unfair Dismissal',
  constructive_dismissal: 'Constructive Dismissal',
  discrimination: 'Discrimination',
  harassment: 'Harassment',
  victimisation: 'Victimisation',
  whistleblowing: 'Whistleblowing',
  breach_of_contract: 'Breach of Contract',
  unpaid_wages: 'Unpaid Wages',
  health_and_safety: 'Health & Safety',
  custom: 'Custom',
};

const STATUS_COLORS: Record<string, string> = {
  active: '#3b82f6',
  abandoned: '#6b7280',
  succeeded: '#16a34a',
  failed: '#dc2626',
  settled: '#d97706',
};

const strengthColor = (s: number) =>
  s >= 75 ? '#16a34a' : s >= 50 ? '#d97706' : s >= 25 ? '#ea580c' : '#dc2626';

export const CasemapPage: React.FC = () => {
  const [theories, setTheories] = useState<Theory[]>([]);
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState<Record<string, any>>({});

  const fetchData = useCallback(async () => {
    try {
      const [thRes, tmplRes] = await Promise.all([
        fetch('/api/casemap/theories'),
        fetch('/api/casemap/templates'),
      ]);
      const thData = await thRes.json();
      const tmplData = await tmplRes.json();
      setTheories(thData.theories || []);
      setTemplates(tmplData.templates || {});
    } catch (err) {
      console.error('Failed to fetch theories:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div style={{ padding: '24px', maxWidth: '1200px' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '24px',
        }}
      >
        <div>
          <h1
            style={{
              fontSize: '24px',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Map size={24} /> Case Map
          </h1>
          <p style={{ color: '#6b7280', marginTop: '4px' }}>
            Map legal theories to evidence with burden of proof tracking
          </p>
        </div>
        <button
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 16px',
            background: '#3b82f6',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: 500,
          }}
        >
          <Plus size={16} /> New Theory
        </button>
      </div>

      {Object.keys(templates).length > 0 && (
        <div
          style={{
            padding: '12px 16px',
            marginBottom: '16px',
            borderRadius: '8px',
            background: '#eff6ff',
            border: '1px solid #bfdbfe',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <Scale size={16} style={{ color: '#2563eb' }} />
          <span style={{ fontSize: '13px', color: '#1e40af' }}>
            {Object.keys(templates).length} claim type templates available with pre-defined legal
            elements
          </span>
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: '48px', color: '#6b7280' }}>
          Loading theories...
        </div>
      ) : theories.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '48px', color: '#6b7280' }}>
          <Map size={48} style={{ marginBottom: '12px', opacity: 0.3 }} />
          <p>No legal theories yet. Create one to start mapping your case.</p>
          <p style={{ fontSize: '13px', marginTop: '8px' }}>
            Available templates:{' '}
            {Object.keys(CLAIM_TYPE_LABELS)
              .filter((k) => k !== 'custom')
              .join(', ')}
          </p>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
            gap: '12px',
          }}
        >
          {theories.map((t) => (
            <div
              key={t.id}
              style={{
                padding: '16px',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                background: 'var(--bg-primary, white)',
                cursor: 'pointer',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '16px' }}>{t.title}</div>
                  <div style={{ fontSize: '13px', color: '#6b7280', marginTop: '2px' }}>
                    {CLAIM_TYPE_LABELS[t.claim_type] || t.claim_type}
                    {t.statutory_basis && ` · ${t.statutory_basis}`}
                  </div>
                </div>
                <span
                  style={{
                    padding: '2px 8px',
                    borderRadius: '12px',
                    fontSize: '12px',
                    fontWeight: 500,
                    background: `${STATUS_COLORS[t.status] || '#6b7280'}15`,
                    color: STATUS_COLORS[t.status] || '#6b7280',
                  }}
                >
                  {t.status}
                </span>
              </div>

              <div style={{ marginTop: '12px' }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '13px',
                    marginBottom: '4px',
                  }}
                >
                  <span style={{ color: '#6b7280' }}>Case Strength</span>
                  <span style={{ fontWeight: 600, color: strengthColor(t.overall_strength) }}>
                    {t.overall_strength}%
                  </span>
                </div>
                <div
                  style={{
                    height: '6px',
                    borderRadius: '3px',
                    background: '#f3f4f6',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${t.overall_strength}%`,
                      borderRadius: '3px',
                      background: strengthColor(t.overall_strength),
                      transition: 'width 0.3s ease',
                    }}
                  />
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginTop: '12px',
                  paddingTop: '12px',
                  borderTop: '1px solid #f3f4f6',
                }}
              >
                <div style={{ display: 'flex', gap: '12px' }}>
                  <button
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '12px',
                      color: '#6b7280',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    <Grid3X3 size={14} /> Matrix
                  </button>
                  <button
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '12px',
                      color: '#6b7280',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    <BarChart3 size={14} /> Strength
                  </button>
                </div>
                <ChevronRight size={16} style={{ color: '#9ca3af' }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
