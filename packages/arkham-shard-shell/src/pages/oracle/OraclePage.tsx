import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';
import type { OracleListItem } from './types';

type TabType = 'sessions' | 'authorities';

interface SessionMetadata {
  query: string;
  results_count: number;
  authority_ids: string[];
}

interface AuthorityMetadata {
  citation: string;
  court_level: 'Supreme Court' | 'Court of Appeal' | 'EAT' | 'ET';
  binding_type: 'binding' | 'persuasive';
  ratio_decidendi: string;
  case_summary: string;
  year?: string | number;
}

const COURT_COLORS: Record<string, string> = {
  'Supreme Court': '#7c3aed',
  'Court of Appeal': '#2563eb',
  EAT: '#059669',
  ET: '#6b7280',
};

export function OraclePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = (searchParams.get('tab') as TabType) || 'sessions';
  const sessionId = searchParams.get('sessionId');
  const authId = searchParams.get('authId');

  const setTab = (tab: TabType) => {
    const params = new URLSearchParams(searchParams);
    params.set('tab', tab);
    params.delete('sessionId');
    params.delete('authId');
    setSearchParams(params);
  };

  const selectSession = (id: string) => {
    const params = new URLSearchParams(searchParams);
    params.set('sessionId', id);
    setSearchParams(params);
  };

  const selectAuthority = (id: string) => {
    const params = new URLSearchParams(searchParams);
    params.set('authId', id);
    setSearchParams(params);
  };

  const clearSelection = () => {
    const params = new URLSearchParams(searchParams);
    params.delete('sessionId');
    params.delete('authId');
    setSearchParams(params);
  };

  if (!!sessionId && activeTab === 'sessions') {
    return (
      <SessionDetailView
        sessionId={sessionId}
        onBack={clearSelection}
        onSelectAuthority={selectAuthority}
      />
    );
  }

  if (authId) {
    return <AuthorityDetailView authId={authId} onBack={clearSelection} />;
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <div
            style={{
              width: '40px',
              height: '40px',
              borderRadius: '8px',
              background: '#f3f4f6',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#374151',
            }}
          >
            <Icon name="Scale" size={24} />
          </div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0 }}>Oracle Legal Research</h1>
        </div>
        <p style={{ color: '#6b7280', margin: 0, fontSize: '15px' }}>
          LLM-powered authority search and ratio decidendi extraction for UK Employment Law.
        </p>
      </header>

      <div
        style={{
          display: 'flex',
          gap: '4px',
          borderBottom: '1px solid #e5e7eb',
          marginBottom: '24px',
        }}
      >
        <button
          onClick={() => setTab('sessions')}
          style={{
            padding: '12px 20px',
            border: 'none',
            background: 'transparent',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: activeTab === 'sessions' ? 600 : 500,
            color: activeTab === 'sessions' ? '#2563eb' : '#6b7280',
            borderBottom: activeTab === 'sessions' ? '2px solid #2563eb' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            transition: 'all 0.2s',
          }}
        >
          <Icon name="MessageSquare" size={16} /> Research Sessions
        </button>
        <button
          onClick={() => setTab('authorities')}
          style={{
            padding: '12px 20px',
            border: 'none',
            background: 'transparent',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: activeTab === 'authorities' ? 600 : 500,
            color: activeTab === 'authorities' ? '#2563eb' : '#6b7280',
            borderBottom:
              activeTab === 'authorities' ? '2px solid #2563eb' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            transition: 'all 0.2s',
          }}
        >
          <Icon name="BookOpen" size={16} /> Authorities Database
        </button>
      </div>

      {activeTab === 'sessions' ? (
        <SessionsTab onSelectSession={selectSession} />
      ) : (
        <AuthoritiesTab onSelectAuthority={selectAuthority} />
      )}
    </div>
  );
}

function SessionsTab({ onSelectSession }: { onSelectSession: (id: string) => void }) {
  const { toast } = useToast();
  const [items, setItems] = useState<OracleListItem[]>([]);
  const [loading, setLoading] = useState(true);

  const loadSessions = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listItems({ type: 'session' });
      setItems(data.items as unknown as OracleListItem[]);
    } catch (err) {
      toast.error(`Failed to load research sessions: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  if (loading) return <LoadingSkeleton />;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      <ResearchLauncher onStarted={(id) => onSelectSession(id)} />

      <div>
        <h2
          style={{
            fontSize: '18px',
            fontWeight: 600,
            marginBottom: '16px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          Recent Investigations
        </h2>
        {items.length === 0 ? (
          <div
            style={{
              padding: '48px',
              textAlign: 'center',
              border: '2px dashed #e5e7eb',
              borderRadius: '12px',
              color: '#9ca3af',
            }}
          >
            <Icon name="Search" size={40} style={{ marginBottom: '12px', opacity: 0.5 }} />
            <p style={{ margin: 0 }}>No research sessions yet. Start one above.</p>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '12px' }}>
            {items.map((item) => (
              <div
                key={item.id}
                onClick={() => onSelectSession(item.id)}
                style={{
                  padding: '16px',
                  borderRadius: '10px',
                  background: '#fff',
                  border: '1px solid #e5e7eb',
                  cursor: 'pointer',
                  transition: 'transform 0.1s, box-shadow 0.1s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow = '0 4px 6px -1px rgba(0, 0, 0, 0.1)';
                  e.currentTarget.style.borderColor = '#d1d5db';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.boxShadow = 'none';
                  e.currentTarget.style.borderColor = '#e5e7eb';
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <h3
                      style={{
                        margin: '0 0 6px 0',
                        fontSize: '15px',
                        fontWeight: 600,
                        color: '#111827',
                      }}
                    >
                      {String(item.title)}
                    </h3>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px',
                        fontSize: '13px',
                        color: '#6b7280',
                      }}
                    >
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Icon name="Calendar" size={12} />
                        {new Date(item.created_at).toLocaleDateString()}
                      </span>
                      {!!item.description && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Icon name="Link" size={12} />
                          {String(item.description)}
                        </span>
                      )}
                    </div>
                  </div>
                  <Icon name="ChevronRight" size={18} color="#d1d5db" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ResearchLauncher({ onStarted }: { onStarted: (id: string) => void }) {
  const { toast } = useToast();
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);

  const handleLaunch = async () => {
    if (!query.trim()) {
      toast.warning('Please enter a research query.');
      return;
    }

    try {
      setBusy(true);
      const result = await api.startResearch({
        project_id: '',
        query: query.trim(),
      });
      toast.success('Research session initiated.');
      onStarted(result.id);
    } catch (err) {
      toast.error(`Failed to start research: ${err}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        background: '#f9fafb',
        borderRadius: '12px',
        padding: '24px',
        border: '1px solid #e5e7eb',
        boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
      }}
    >
      <h3 style={{ margin: '0 0 12px 0', fontSize: '16px', fontWeight: 600 }}>
        New Legal Research
      </h3>
      <div style={{ position: 'relative' }}>
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. What is the leading authority on the definition of 'disability' under s.6 of the Equality Act 2010?"
          style={{
            width: '100%',
            minHeight: '120px',
            padding: '14px',
            borderRadius: '8px',
            border: '1px solid #d1d5db',
            fontSize: '14px',
            lineHeight: '1.5',
            boxSizing: 'border-box',
            marginBottom: '12px',
            resize: 'vertical',
            fontFamily: 'inherit',
          }}
        />
        <div
          style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '12px' }}
        >
          <span style={{ fontSize: '12px', color: '#6b7280' }}>
            Natural language input supported
          </span>
          <button
            onClick={handleLaunch}
            disabled={busy || !query.trim()}
            style={{
              padding: '10px 20px',
              borderRadius: '6px',
              background: '#2563eb',
              color: 'white',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '14px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              opacity: busy ? 0.7 : 1,
              transition: 'background 0.2s',
            }}
          >
            {busy ? (
              <Icon name="Loader2" size={16} className="animate-spin" />
            ) : (
              <Icon name="Zap" size={16} />
            )}
            {busy ? 'Searching Authorities...' : 'Launch Authority Search'}
          </button>
        </div>
      </div>
    </div>
  );
}

function AuthoritiesTab({ onSelectAuthority }: { onSelectAuthority: (id: string) => void }) {
  const { toast } = useToast();
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  const loadAuthorities = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listAuthorities('');
      setItems(data);
    } catch (err) {
      toast.error(`Failed to load authorities: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadAuthorities();
  }, [loadAuthorities]);

  if (loading) return <LoadingSkeleton />;

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '16px',
        }}
      >
        <h2 style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>Cited Authorities</h2>
        <div style={{ display: 'flex', gap: '8px' }}>
          <div
            style={{
              fontSize: '12px',
              color: '#6b7280',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <span
              style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#7c3aed' }}
            />{' '}
            Supreme
          </div>
          <div
            style={{
              fontSize: '12px',
              color: '#6b7280',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <span
              style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#2563eb' }}
            />{' '}
            CoA
          </div>
          <div
            style={{
              fontSize: '12px',
              color: '#6b7280',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <span
              style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#059669' }}
            />{' '}
            EAT
          </div>
        </div>
      </div>

      {items.length === 0 ? (
        <div
          style={{
            padding: '48px',
            textAlign: 'center',
            background: '#f9fafb',
            borderRadius: '12px',
          }}
        >
          <p style={{ color: '#6b7280', margin: 0 }}>No authorities found in the database.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {items.map((auth) => {
            const meta = (auth.metadata || {}) as AuthorityMetadata;
            const court = String(meta.court_level || 'ET');
            const courtConfig = COURT_COLORS[court] || COURT_COLORS['ET'];
            const isBinding = meta.binding_type === 'binding';

            return (
              <div
                key={String(auth.id)}
                onClick={() => onSelectAuthority(String(auth.id))}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '14px 16px',
                  borderRadius: '8px',
                  border: '1px solid #e5e7eb',
                  background: 'white',
                  cursor: 'pointer',
                  borderLeft: `4px solid ${courtConfig}`,
                }}
              >
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      marginBottom: '4px',
                    }}
                  >
                    <span style={{ fontWeight: 700, fontSize: '15px', fontStyle: 'italic' }}>
                      {String(auth.title || meta.citation || 'Unknown Case')}
                    </span>
                    <span
                      style={{
                        fontSize: '11px',
                        padding: '2px 8px',
                        borderRadius: '12px',
                        background: isBinding ? '#fee2e2' : '#f3f4f6',
                        color: isBinding ? '#dc2626' : '#6b7280',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                      }}
                    >
                      {String(meta.binding_type || 'persuasive')}
                    </span>
                  </div>
                  <div style={{ fontSize: '13px', color: '#6b7280', fontFamily: 'monospace' }}>
                    {String(meta.citation || '')} {!!meta.year && `[${String(meta.year)}]`}
                  </div>
                </div>
                <div
                  style={{ textAlign: 'right', display: 'flex', alignItems: 'center', gap: '16px' }}
                >
                  <div
                    style={{
                      fontSize: '11px',
                      fontWeight: 700,
                      padding: '4px 10px',
                      borderRadius: '4px',
                      background: courtConfig,
                      color: 'white',
                    }}
                  >
                    {court}
                  </div>
                  <Icon name="ChevronRight" size={18} color="#d1d5db" />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SessionDetailView({
  sessionId,
  onBack,
  onSelectAuthority,
}: {
  sessionId: string;
  onBack: () => void;
  onSelectAuthority: (id: string) => void;
}) {
  const { toast } = useToast();
  const [item, setItem] = useState<Record<string, unknown> | null>(null);
  const [authorities, setAuthorities] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const sessionData = await api.getSession(sessionId);
        setItem(sessionData);

        const meta = (sessionData.metadata || {}) as SessionMetadata;
        if (!!meta.authority_ids && meta.authority_ids.length > 0) {
          const authPromises = meta.authority_ids
            .slice(0, 10)
            .map((id) => api.getAuthority(id).catch(() => null));
          const authResults = await Promise.all(authPromises);
          setAuthorities(authResults.filter((a) => a !== null) as Record<string, unknown>[]);
        }
      } catch (err) {
        toast.error(`Failed to load session details: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionId, toast]);

  if (loading) return <LoadingSkeleton />;
  if (!item) return <div style={{ padding: '24px' }}>Session not found.</div>;

  const meta = (item.metadata || {}) as SessionMetadata;

  return (
    <div style={{ padding: '24px', maxWidth: '1000px', margin: '0 auto' }}>
      <button
        onClick={onBack}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          background: 'none',
          border: 'none',
          color: '#2563eb',
          cursor: 'pointer',
          fontSize: '14px',
          fontWeight: 600,
          padding: 0,
          marginBottom: '24px',
        }}
      >
        <Icon name="ArrowLeft" size={16} /> Back to Sessions
      </button>

      <div
        style={{
          background: 'white',
          borderRadius: '12px',
          border: '1px solid #e5e7eb',
          padding: '24px',
          marginBottom: '32px',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            color: '#6b7280',
            fontSize: '13px',
            marginBottom: '12px',
          }}
        >
          <Icon name="Clock" size={14} /> Investigation started{' '}
          {new Date(String(item.created_at)).toLocaleString()}
        </div>
        <h1 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 16px 0', lineHeight: '1.4' }}>
          {String(meta.query || item.title || 'Untitled Investigation')}
        </h1>
        <div style={{ display: 'flex', gap: '16px' }}>
          <div
            style={{
              padding: '12px 20px',
              background: '#f0f9ff',
              borderRadius: '8px',
              border: '1px solid #bae6fd',
            }}
          >
            <div
              style={{
                fontSize: '12px',
                color: '#0369a1',
                fontWeight: 700,
                textTransform: 'uppercase',
                marginBottom: '4px',
              }}
            >
              Authorities Found
            </div>
            <div style={{ fontSize: '24px', fontWeight: 800, color: '#0369a1' }}>
              {String(meta.results_count || 0)}
            </div>
          </div>
        </div>
      </div>

      <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>
        Relevant Authorities
      </h2>
      {authorities.length === 0 ? (
        <div
          style={{
            padding: '32px',
            textAlign: 'center',
            background: '#f9fafb',
            borderRadius: '12px',
            color: '#9ca3af',
          }}
        >
          <p>No authorities were identified for this query.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {authorities.map((auth, idx) => {
            const aMeta = (auth.metadata || {}) as AuthorityMetadata;
            const court = String(aMeta.court_level || 'ET');
            const courtConfig = COURT_COLORS[court] || COURT_COLORS['ET'];

            return (
              <div
                key={String(auth.id || idx)}
                onClick={() => onSelectAuthority(String(auth.id))}
                style={{
                  padding: '16px',
                  borderRadius: '10px',
                  background: 'white',
                  border: '1px solid #e5e7eb',
                  cursor: 'pointer',
                  transition: 'box-shadow 0.2s',
                }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.boxShadow = '0 2px 4px rgba(0,0,0,0.05)')
                }
                onMouseLeave={(e) => (e.currentTarget.style.boxShadow = 'none')}
              >
                <div
                  style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}
                >
                  <div style={{ fontWeight: 700, fontStyle: 'italic', color: '#111827' }}>
                    {String(auth.title || aMeta.citation || 'Unknown Case')}
                  </div>
                  <div
                    style={{
                      fontSize: '10px',
                      fontWeight: 800,
                      padding: '2px 8px',
                      borderRadius: '4px',
                      background: courtConfig,
                      color: 'white',
                    }}
                  >
                    {court}
                  </div>
                </div>
                <div
                  style={{
                    fontSize: '13px',
                    color: '#4b5563',
                    marginBottom: '12px',
                    lineHeight: '1.5',
                  }}
                >
                  {String(aMeta.ratio_decidendi || 'No ratio extracted for this case.')}
                </div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    fontSize: '12px',
                    color: '#9ca3af',
                  }}
                >
                  <span style={{ fontFamily: 'monospace' }}>{String(aMeta.citation || '')}</span>
                  {!!aMeta.binding_type && (
                    <span
                      style={{
                        padding: '1px 6px',
                        borderRadius: '4px',
                        background: '#f3f4f6',
                        color: aMeta.binding_type === 'binding' ? '#dc2626' : '#6b7280',
                        fontWeight: 600,
                      }}
                    >
                      {String(aMeta.binding_type)}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function AuthorityDetailView({ authId, onBack }: { authId: string; onBack: () => void }) {
  const { toast } = useToast();
  const [item, setItem] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const data = await api.getAuthority(authId);
        setItem(data);
      } catch (err) {
        toast.error(`Failed to load authority: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [authId, toast]);

  if (loading) return <LoadingSkeleton />;
  if (!item) return <div style={{ padding: '24px' }}>Authority not found.</div>;

  const meta = (item.metadata || {}) as AuthorityMetadata;
  const court = String(meta.court_level || 'ET');
  const courtColor = COURT_COLORS[court] || COURT_COLORS['ET'];
  const isBinding = meta.binding_type === 'binding';

  return (
    <div style={{ padding: '24px', maxWidth: '900px', margin: '0 auto' }}>
      <button
        onClick={onBack}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          background: 'none',
          border: 'none',
          color: '#2563eb',
          cursor: 'pointer',
          fontSize: '14px',
          fontWeight: 600,
          padding: 0,
          marginBottom: '24px',
        }}
      >
        <Icon name="ArrowLeft" size={16} /> Back to List
      </button>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <div
          style={{
            background: 'white',
            borderRadius: '16px',
            border: '1px solid #e5e7eb',
            overflow: 'hidden',
          }}
        >
          <div style={{ height: '6px', background: courtColor }} />
          <div style={{ padding: '32px' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                marginBottom: '16px',
              }}
            >
              <div>
                <h1
                  style={{
                    fontSize: '28px',
                    fontWeight: 800,
                    margin: '0 0 8px 0',
                    fontStyle: 'italic',
                    color: '#111827',
                  }}
                >
                  {String(item.title || meta.citation || 'Unknown Case')}
                </h1>
                <div style={{ fontSize: '16px', color: '#6b7280', fontFamily: 'monospace' }}>
                  {String(meta.citation || '')} {!!meta.year && `(${String(meta.year)})`}
                </div>
              </div>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                  alignItems: 'flex-end',
                }}
              >
                <div
                  style={{
                    padding: '6px 16px',
                    borderRadius: '6px',
                    background: courtColor,
                    color: 'white',
                    fontWeight: 800,
                    fontSize: '13px',
                  }}
                >
                  {court}
                </div>
                <div
                  style={{
                    padding: '4px 12px',
                    borderRadius: '20px',
                    border: `1px solid ${isBinding ? '#dc2626' : '#d1d5db'}`,
                    color: isBinding ? '#dc2626' : '#6b7280',
                    fontWeight: 700,
                    fontSize: '11px',
                    textTransform: 'uppercase',
                    background: isBinding ? '#fef2f2' : 'transparent',
                  }}
                >
                  {String(meta.binding_type || 'persuasive')}
                </div>
              </div>
            </div>

            <hr style={{ border: 'none', borderTop: '1px solid #f3f4f6', margin: '24px 0' }} />

            <section style={{ marginBottom: '32px' }}>
              <h3
                style={{
                  fontSize: '12px',
                  fontWeight: 800,
                  color: '#374151',
                  textTransform: 'uppercase',
                  letterSpacing: '1px',
                  marginBottom: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <Icon name="Target" size={14} color={courtColor} /> Ratio Decidendi
              </h3>
              <div
                style={{
                  padding: '20px',
                  background: '#f8fafc',
                  borderRadius: '12px',
                  borderLeft: `4px solid ${courtColor}`,
                  fontSize: '16px',
                  lineHeight: '1.6',
                  color: '#1e293b',
                  fontWeight: 500,
                }}
              >
                {String(
                  meta.ratio_decidendi || 'The ratio for this authority has not been extracted yet.'
                )}
              </div>
            </section>

            <section>
              <h3
                style={{
                  fontSize: '12px',
                  fontWeight: 800,
                  color: '#374151',
                  textTransform: 'uppercase',
                  letterSpacing: '1px',
                  marginBottom: '12px',
                }}
              >
                Case Summary
              </h3>
              <div
                style={{
                  fontSize: '15px',
                  lineHeight: '1.7',
                  color: '#4b5563',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {String(
                  meta.case_summary ||
                    item.description ||
                    'Detailed case summary is currently unavailable.'
                )}
              </div>
            </section>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          <button
            style={{
              padding: '10px 16px',
              borderRadius: '6px',
              background: 'white',
              border: '1px solid #d1d5db',
              color: '#374151',
              fontSize: '14px',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Icon name="Download" size={16} /> Export Citation
          </button>
          <button
            style={{
              padding: '10px 16px',
              borderRadius: '6px',
              background: '#2563eb',
              border: 'none',
              color: 'white',
              fontSize: '14px',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Icon name="FileText" size={16} /> View Full Judgment
          </button>
        </div>
      </div>
    </div>
  );
}
