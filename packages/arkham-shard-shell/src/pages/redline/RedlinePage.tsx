/**
 * RedlinePage - Document comparison and redlining tool
 *
 * Detects silent edits between document versions and visualizes document evolution chains.
 */

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';

// --- Types (Internal) ---

type Significance = 'high' | 'medium' | 'low';
type ChangeType = 'added' | 'removed' | 'modified';

interface Change {
  id: string;
  type: ChangeType;
  text: string;
  previous_text?: string;
  significance: Significance;
  significance_score: number;
  reasoning: string;
  context: string;
}

interface ComparisonData {
  id: string;
  title: string;
  description: string;
  base_document_id: string;
  target_document_id: string;
  base_document_title: string;
  target_document_title: string;
  changes: Change[];
  stats: {
    additions: number;
    deletions: number;
    modifications: number;
    total: number;
  };
  silent_edits: string[];
  created_at: string;
  metadata?: Record<string, unknown>;
}

interface ChainVersion {
  id: string;
  version_number: number;
  document_id: string;
  title: string;
  created_at: string;
  created_by: string;
  comparison_to_prev_id?: string;
}

interface ChainData {
  id: string;
  title: string;
  description: string;
  versions: ChainVersion[];
}

// --- Styles (Inline) ---

const styles = {
  container: {
    padding: '24px',
    maxWidth: '1200px',
    margin: '0 auto',
    fontFamily: 'system-ui, -apple-system, sans-serif',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '24px',
  },
  title: {
    fontSize: '24px',
    fontWeight: 700,
    margin: 0,
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    color: 'var(--arkham-text-primary, #111827)',
  },
  subtitle: {
    fontSize: '14px',
    color: 'var(--arkham-text-muted, #6b7280)',
    marginTop: '4px',
  },
  tabs: {
    display: 'flex',
    gap: '24px',
    borderBottom: '1px solid var(--arkham-border, #e5e7eb)',
    marginBottom: '24px',
  },
  tab: (active: boolean) => ({
    padding: '12px 4px',
    fontSize: '14px',
    fontWeight: 600,
    color: active ? '#3b82f6' : 'var(--arkham-text-muted, #6b7280)',
    borderBottom: `2px solid ${active ? '#3b82f6' : 'transparent'}`,
    cursor: 'pointer',
    background: 'none',
    borderTop: 'none',
    borderLeft: 'none',
    borderRight: 'none',
    transition: 'all 0.2s',
  }),
  button: {
    padding: '8px 16px',
    borderRadius: '6px',
    fontWeight: 500,
    fontSize: '14px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    border: 'none',
    backgroundColor: '#3b82f6',
    color: 'white',
  },
  card: {
    backgroundColor: 'var(--arkham-bg-secondary, #ffffff)',
    border: '1px solid var(--arkham-border, #e5e7eb)',
    borderRadius: '12px',
    padding: '16px',
    marginBottom: '12px',
    cursor: 'pointer',
    transition: 'transform 0.1s, box-shadow 0.1s',
  },
  badge: (type: 'addition' | 'deletion' | 'modification' | 'alert') => {
    const colors = {
      addition: { bg: '#ecfdf5', text: '#059669' },
      deletion: { bg: '#fef2f2', text: '#dc2626' },
      modification: { bg: '#eff6ff', text: '#2563eb' },
      alert: { bg: '#fffbeb', text: '#d97706' },
    };
    const c = colors[type];
    return {
      backgroundColor: c.bg,
      color: c.text,
      padding: '2px 8px',
      borderRadius: '12px',
      fontSize: '11px',
      fontWeight: 700,
      textTransform: 'uppercase' as const,
    };
  },
  significanceBadge: (level: Significance) => {
    const colors = {
      high: { bg: '#fef2f2', text: '#dc2626', border: '#fecaca' },
      medium: { bg: '#fffbeb', text: '#d97706', border: '#fde68a' },
      low: { bg: '#f3f4f6', text: '#4b5563', border: '#e5e7eb' },
    };
    const c = colors[level];
    return {
      backgroundColor: c.bg,
      color: c.text,
      border: `1px solid ${c.border}`,
      padding: '2px 8px',
      borderRadius: '4px',
      fontSize: '11px',
      fontWeight: 600,
    };
  },
  alertPanel: {
    backgroundColor: '#fffbeb',
    border: '1px solid #fde68a',
    borderRadius: '8px',
    padding: '16px',
    marginBottom: '24px',
    display: 'flex',
    gap: '12px',
  },
  timeline: {
    position: 'relative' as const,
    paddingLeft: '32px',
    marginLeft: '12px',
    borderLeft: '2px solid var(--arkham-border, #e5e7eb)',
  },
  timelineNode: {
    position: 'relative' as const,
    marginBottom: '24px',
  },
  timelineDot: {
    position: 'absolute' as const,
    left: '-41px',
    top: '4px',
    width: '16px',
    height: '16px',
    borderRadius: '50%',
    backgroundColor: 'white',
    border: '2px solid #3b82f6',
    zIndex: 1,
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
    gap: '16px',
  },
};

// --- Main Page Component ---

export function RedlinePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const compId = searchParams.get('compId');
  const chainId = searchParams.get('chainId');
  const activeTab = searchParams.get('tab') || 'comparisons';

  const setTab = (tab: string) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('tab', tab);
    setSearchParams(nextParams);
  };

  if (!!compId && compId !== "") {
    return <ComparisonDetailView compId={compId} onBack={() => {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete('compId');
      setSearchParams(nextParams);
    }} />;
  }

  if (!!chainId && chainId !== "") {
    return <ChainDetailView chainId={chainId} onBack={() => {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete('chainId');
      setSearchParams(nextParams);
    }} />;
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>
            <Icon name="FileDiff" size={28} /> Redline
          </h1>
          <p style={styles.subtitle}>Detect document version evolution and silent edits</p>
        </div>
      </div>

      <div style={styles.tabs}>
        <button
          style={styles.tab(activeTab === 'comparisons')}
          onClick={() => setTab('comparisons')}
        >
          Comparisons
        </button>
        <button
          style={styles.tab(activeTab === 'chains')}
          onClick={() => setTab('chains')}
        >
          Version Chains
        </button>
      </div>

      {activeTab === 'comparisons' ? <ComparisonListView /> : <ChainListView />}
    </div>
  );
}

// --- List Views ---

function ComparisonListView() {
  const { toast } = useToast();
  const [items, setItems] = useState<ComparisonData[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [, setSearchParams] = useSearchParams();

  const loadComparisons = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.listItems({ type: 'comparison' });
      const mapped = (res.items || []).map(it => ({
        id: String(it.id || ''),
        title: String(it.title || 'Untitled Comparison'),
        description: String(it.description || ''),
        base_document_title: String(it.base_document_title || 'Original'),
        target_document_title: String(it.target_document_title || 'Revised'),
        stats: {
          additions: Number((it.metadata as any)?.stats?.additions || 0),
          deletions: Number((it.metadata as any)?.stats?.deletions || 0),
          modifications: Number((it.metadata as any)?.stats?.modifications || 0),
          total: Number((it.metadata as any)?.stats?.total || 0),
        },
        created_at: String(it.created_at || ''),
      })) as ComparisonData[];
      setItems(mapped);
    } catch (err) {
      toast.error(`Failed to load comparisons: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadComparisons();
  }, [loadComparisons]);

  const handleSelect = (id: string) => {
    const params = new URLSearchParams(window.location.search);
    params.set('compId', id);
    setSearchParams(params);
  };

  if (loading) return <LoadingSkeleton />;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '16px' }}>
        <button style={styles.button} onClick={() => setShowCreate(true)}>
          <Icon name="Plus" size={16} /> New Comparison
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState icon="FileDiff" message="No comparisons found" submessage="Create a comparison between two document versions." />
      ) : (
        <div style={styles.grid}>
          {items.map((item) => (
            <div key={item.id} style={styles.card} onClick={() => handleSelect(item.id)}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>{item.title}</h3>
                <span style={{ fontSize: '11px', color: 'var(--arkham-text-muted)' }}>
                  {new Date(item.created_at).toLocaleDateString()}
                </span>
              </div>
              <p style={{ fontSize: '13px', color: 'var(--arkham-text-muted)', marginBottom: '16px', height: '36px', overflow: 'hidden' }}>
                {item.description}
              </p>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <span style={styles.badge('addition')}>+{item.stats.additions}</span>
                <span style={styles.badge('deletion')}>-{item.stats.deletions}</span>
                <span style={styles.badge('modification')}>~{item.stats.modifications}</span>
              </div>
              <div style={{ marginTop: '12px', fontSize: '12px', borderTop: '1px solid var(--arkham-border)', paddingTop: '8px', color: 'var(--arkham-text-muted)' }}>
                {item.base_document_title} <Icon name="ArrowRight" size={10} /> {item.target_document_title}
              </div>
            </div>
          ))}
        </div>
      )}

      {!!showCreate && (
        <CreateComparisonDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            loadComparisons();
          }}
        />
      )}
    </div>
  );
}

function ChainListView() {
  const { toast } = useToast();
  const [chains, setChains] = useState<ChainData[]>([]);
  const [loading, setLoading] = useState(true);
  const [, setSearchParams] = useSearchParams();

  const loadChains = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams(window.location.search);
      const projectId = params.get('project_id') || params.get('projectId');
      if (!projectId) {
        toast.error("Project ID required for chains");
        setLoading(false);
        return;
      }
      const res = await api.listChains(projectId);
      setChains(res.map(c => ({
        id: String(c.id || ''),
        title: String(c.title || 'Untitled Chain'),
        description: String(c.description || ''),
            versions: (c.versions as any[] || []).map(v => ({
              id: String(v.id || ''),
              version_number: Number(v.version_number || 0),
              document_id: String(v.document_id || ''),
              title: String(v.title || ''),
              created_at: String(v.created_at || ''),
              created_by: String(v.created_by || ''),
            })),
      })));
    } catch (err) {
      toast.error(`Failed to load version chains: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadChains();
  }, [loadChains]);

  const handleSelect = (id: string) => {
    const params = new URLSearchParams(window.location.search);
    params.set('chainId', id);
    setSearchParams(params);
  };

  if (loading) return <LoadingSkeleton />;

  return (
    <div>
      {chains.length === 0 ? (
        <EmptyState icon="GitBranch" message="No version chains found" submessage=" Chards will automatically track versions of the same document name." />
      ) : (
        <div style={styles.grid}>
          {chains.map((chain) => (
            <div key={chain.id} style={styles.card} onClick={() => handleSelect(chain.id)}>
              <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>{chain.title}</h3>
              <p style={{ fontSize: '13px', color: 'var(--arkham-text-muted)', marginBottom: '12px' }}>
                {chain.description}
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Icon name="Layers" size={14} color="#6b7280" />
                <span style={{ fontSize: '13px', fontWeight: 500 }}>{chain.versions.length} versions</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Detail Views ---

function ComparisonDetailView({ compId, onBack }: { compId: string; onBack: () => void }) {
  const { toast } = useToast();
  const [data, setData] = useState<ComparisonData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const res = await api.getComparison(compId);
        // Map raw API response to ComparisonData
        const mapped: ComparisonData = {
          id: String(res.id || compId),
          title: String(res.title || 'Comparison'),
          description: String(res.description || ''),
          base_document_id: String(res.base_document_id || ''),
          target_document_id: String(res.target_document_id || ''),
          base_document_title: String(res.base_document_title || 'Original'),
          target_document_title: String(res.target_document_title || 'Revised'),
          changes: (res.changes as any[] || []).map(ch => ({
            id: String(ch.id || Math.random().toString()),
            type: (ch.type as ChangeType) || 'modified',
            text: String(ch.text || ''),
            previous_text: ch.previous_text ? String(ch.previous_text) : undefined,
            significance: (ch.significance as Significance) || 'low',
            significance_score: Number(ch.significance_score || 0),
            reasoning: String(ch.reasoning || ''),
            context: String(ch.context || ''),
          })),
          stats: {
            additions: Number((res.stats as any)?.additions || 0),
            deletions: Number((res.stats as any)?.deletions || 0),
            modifications: Number((res.stats as any)?.modifications || 0),
            total: Number((res.stats as any)?.total || 0),
          },
          silent_edits: (res.silent_edits as string[] || []),
          created_at: String(res.created_at || ''),
        };
        setData(mapped);
      } catch (err) {
        toast.error(`Failed to load comparison: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [compId, toast]);

  if (loading) return <LoadingSkeleton />;
  if (!data) return <div style={styles.container}>Comparison not found</div>;

  return (
    <div style={styles.container}>
      <button
        onClick={onBack}
        style={{
          display: 'flex', alignItems: 'center', gap: '4px',
          background: 'none', border: 'none', color: '#3b82f6',
          cursor: 'pointer', marginBottom: '16px', fontSize: '14px',
          padding: 0
        }}
      >
        <Icon name="ChevronLeft" size={16} /> Back to list
      </button>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 700, margin: 0 }}>{data.title}</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '14px', color: 'var(--arkham-text-muted)' }}>
              <Icon name="FileText" size={14} /> {data.base_document_title}
              <Icon name="ArrowRight" size={12} />
              <Icon name="FileText" size={14} /> {data.target_document_title}
            </div>
            <div style={{ height: '4px', width: '4px', borderRadius: '50%', backgroundColor: '#d1d5db' }} />
            <span style={{ fontSize: '13px', color: 'var(--arkham-text-muted)' }}>
              {new Date(data.created_at).toLocaleString()}
            </span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <div style={styles.badge('addition')}>+{data.stats.additions}</div>
          <div style={styles.badge('deletion')}>-{data.stats.deletions}</div>
          <div style={styles.badge('modification')}>~{data.stats.modifications}</div>
        </div>
      </div>

      {data.silent_edits.length > 0 && (
        <div style={styles.alertPanel}>
          <Icon name="AlertTriangle" size={20} color="#d97706" />
          <div>
            <h4 style={{ margin: '0 0 4px 0', fontSize: '15px', color: '#92400e', fontWeight: 600 }}>Silent Edits Detected</h4>
            <p style={{ margin: 0, fontSize: '13px', color: '#b45309' }}>
              The following changes were made without explicit disclosure or marking in the revised document:
            </p>
            <ul style={{ margin: '8px 0 0 0', paddingLeft: '20px', fontSize: '13px', color: '#b45309' }}>
              {data.silent_edits.map((edit, idx) => (
                <li key={idx}>{edit}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Icon name="List" size={18} /> Detailed Changes ({data.changes.length})
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {data.changes.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', background: 'var(--arkham-bg-tertiary)', borderRadius: '8px' }}>
            No significant changes detected between these versions.
          </div>
        ) : (
          data.changes.map((change) => (
            <ChangeItem key={change.id} change={change} />
          ))
        )}
      </div>
    </div>
  );
}

function ChangeItem({ change }: { change: Change }) {
  const [expanded, setExpanded] = useState(false);

  const getIcon = () => {
    if (change.type === 'added') return <Icon name="PlusCircle" size={16} color="#059669" />;
    if (change.type === 'removed') return <Icon name="MinusCircle" size={16} color="#dc2626" />;
    return <Icon name="HelpCircle" size={16} color="#2563eb" />;
  };

  return (
    <div style={{
      ...styles.card,
      cursor: 'default',
      padding: '16px',
      borderLeft: `4px solid ${change.type === 'added' ? '#059669' : change.type === 'removed' ? '#dc2626' : '#3b82f6'}`
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            {getIcon()}
            <span style={{ fontWeight: 600, fontSize: '14px', textTransform: 'capitalize' }}>{change.type}</span>
            <div style={styles.significanceBadge(change.significance)}>
              {change.significance} significance
            </div>
          </div>

          <div style={{
            fontSize: '14px',
            lineHeight: '1.5',
            padding: '8px',
            borderRadius: '4px',
            backgroundColor: change.type === 'added' ? '#f0fdf4' : change.type === 'removed' ? '#fef2f2' : '#f8fafc',
            border: `1px dashed ${change.type === 'added' ? '#bcf0da' : change.type === 'removed' ? '#fecaca' : '#cbd5e1'}`,
            marginBottom: '8px'
          }}>
            {!!change.previous_text && (
              <div style={{ color: '#94a3b8', textDecoration: 'line-through', marginBottom: '4px' }}>
                {change.previous_text}
              </div>
            )}
            <div style={{ fontWeight: 500 }}>{change.text}</div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={() => setExpanded(!expanded)}
              style={{ background: 'none', border: 'none', color: '#3b82f6', fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', padding: 0 }}
            >
              {expanded ? 'Hide reasoning' : 'Show AI analysis'}
              <Icon name={expanded ? "ChevronUp" : "ChevronDown"} size={12} />
            </button>
          </div>

          {!!expanded && (
            <div style={{ marginTop: '12px', fontSize: '13px', color: 'var(--arkham-text-muted)', borderTop: '1px solid var(--arkham-border)', paddingTop: '12px' }}>
              <div style={{ marginBottom: '8px' }}>
                <strong style={{ display: 'block', color: 'var(--arkham-text-primary)' }}>Reasoning:</strong>
                {change.reasoning}
              </div>
              <div>
                <strong style={{ display: 'block', color: 'var(--arkham-text-primary)' }}>Context:</strong>
                {change.context}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ChainDetailView({ chainId, onBack }: { chainId: string; onBack: () => void }) {
  const { toast } = useToast();
  const [chain, setChain] = useState<ChainData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        // Find chain in list or fetch from API
        // For simplicity, we fetch all and find
        const params = new URLSearchParams(window.location.search);
        const projectId = params.get('project_id') || params.get('projectId');
        if (!projectId) return;

        const res = await api.listChains(projectId);
        const found = res.find(c => String(c.id) === chainId);

        if (found) {
          setChain({
            id: String(found.id || ''),
            title: String(found.title || ''),
            description: String(found.description || ''),
            versions: (found.versions as any[] || []).map(v => ({
              id: String(v.id || ''),
              version_number: Number(v.version_number || 0),
              document_id: String(v.document_id || ''),
              title: String(v.title || ''),
              created_at: String(v.created_at || ''),
              created_by: String(v.created_by || ''),
              comparison_to_prev_id: v.comparison_to_prev_id ? String(v.comparison_to_prev_id) : undefined,
            })),
          });
        }
      } catch (err) {
        toast.error(`Failed to load chain: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [chainId, toast]);

  if (loading) return <LoadingSkeleton />;
  if (!chain) return <div style={styles.container}>Chain not found</div>;

  return (
    <div style={styles.container}>
      <button
        onClick={onBack}
        style={{
          display: 'flex', alignItems: 'center', gap: '4px',
          background: 'none', border: 'none', color: '#3b82f6',
          cursor: 'pointer', marginBottom: '16px', fontSize: '14px',
          padding: 0
        }}
      >
        <Icon name="ChevronLeft" size={16} /> Back to list
      </button>

      <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '8px' }}>{chain.title}</h1>
      <p style={{ color: 'var(--arkham-text-muted)', marginBottom: '32px' }}>{chain.description}</p>

      <div style={styles.timeline}>
        {chain.versions.sort((a, b) => b.version_number - a.version_number).map((v) => (
          <div key={v.id} style={styles.timelineNode}>
            <div style={styles.timelineDot} />
            <div style={{ ...styles.card, margin: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <span style={{ fontSize: '11px', fontWeight: 700, color: '#3b82f6', textTransform: 'uppercase' }}>Version {v.version_number}</span>
                  <h4 style={{ margin: '4px 0', fontSize: '16px', fontWeight: 600 }}>{v.title}</h4>
                  <div style={{ display: 'flex', gap: '12px', fontSize: '12px', color: 'var(--arkham-text-muted)' }}>
                    <span>{new Date(v.created_at).toLocaleString()}</span>
                    {!!v.created_by && <span>By {v.created_by}</span>}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {!!v.comparison_to_prev_id && (
                    <button
                      onClick={() => {
                        const params = new URLSearchParams(window.location.search);
                        params.set('compId', v.comparison_to_prev_id!);
                        window.history.pushState({}, '', `?${params.toString()}`);
                        // Force a re-render or just use navigate
                        window.location.reload();
                      }}
                      style={{
                        padding: '6px 12px', borderRadius: '4px', border: '1px solid #3b82f6',
                        background: '#eff6ff', color: '#3b82f6', fontSize: '12px', fontWeight: 500, cursor: 'pointer'
                      }}
                    >
                      View Redline to V{v.version_number - 1}
                    </button>
                  )}
                  <button style={{ padding: '6px 12px', borderRadius: '4px', border: '1px solid var(--arkham-border)', background: 'white', fontSize: '12px', cursor: 'pointer' }}>
                    View Document
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Dialogs ---

function CreateComparisonDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [title, setTitle] = useState('');
  const [baseDocId, setBaseDocId] = useState('');
  const [targetDocId, setTargetDocId] = useState('');
  const [saving, setSaving] = useState(false);
  const [documents, setDocuments] = useState<{ id: string; title: string }[]>([]);

  useEffect(() => {
    (async () => {
      try {
        // We need documents to select from. Using the generic item list or specialized doc service
        // For this implementation we'll try to list items from redline or mock
        const res = await api.listItems();
        setDocuments((res.items || []).map(it => ({ id: String(it.id), title: String(it.title) })));
      } catch (err) {
        console.error(err);
      }
    })();
  }, []);

  const handleCreate = async () => {
    if (!title) return toast.error("Title required");
    if (!baseDocId || !targetDocId) return toast.error("Both documents required");

    try {
      setSaving(true);
      const params = new URLSearchParams(window.location.search);
      const projectId = params.get('project_id') || params.get('projectId') || 'default';

      await api.createComparison({
        project_id: projectId,
        title: title,
        base_document_id: baseDocId,
        target_document_id: targetDocId
      } as any); // Using extra field 'title' which might be supported by backend

      toast.success("Comparison started");
      onCreated();
    } catch (err) {
      toast.error(`Failed to create comparison: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ backgroundColor: 'white', padding: '24px', borderRadius: '12px', width: '480px', maxWidth: '90vw' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 20px 0' }}>New Comparison</h2>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, marginBottom: '6px' }}>Comparison Title</label>
          <input
            style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--arkham-border)', boxSizing: 'border-box' }}
            value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Contract V2 vs V1"
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, marginBottom: '6px' }}>Base Version</label>
            <select
              style={{ width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid var(--arkham-border)' }}
              value={baseDocId} onChange={e => setBaseDocId(e.target.value)}
            >
              <option value="">Select Document...</option>
              {documents.map(d => <option key={d.id} value={d.id}>{d.title}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, marginBottom: '6px' }}>Target Version</label>
            <select
              style={{ width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid var(--arkham-border)' }}
              value={targetDocId} onChange={e => setTargetDocId(e.target.value)}
            >
              <option value="">Select Document...</option>
              {documents.map(d => <option key={d.id} value={d.id}>{d.title}</option>)}
            </select>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
          <button style={{ ...styles.button, backgroundColor: 'transparent', color: 'var(--arkham-text-muted)', border: '1px solid var(--arkham-border)' }} onClick={onClose}>
            Cancel
          </button>
          <button style={{ ...styles.button }} onClick={handleCreate} disabled={saving}>
            {saving ? 'Creating...' : 'Start Comparison'}
          </button>
        </div>
      </div>
    </div>
  );
}

// --- Helpers ---

function EmptyState({ icon, message, submessage }: { icon: string; message: string; submessage: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '64px 24px', backgroundColor: 'var(--arkham-bg-tertiary)', borderRadius: '12px', border: '2px dashed var(--arkham-border)' }}>
      <Icon name={icon} size={48} color="#9ca3af" />
      <h3 style={{ fontSize: '18px', fontWeight: 600, margin: '16px 0 8px 0' }}>{message}</h3>
      <p style={{ fontSize: '14px', color: '#6b7280', margin: 0 }}>{submessage}</p>
    </div>
  );
}
