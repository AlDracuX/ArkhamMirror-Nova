/**
 * PlaybookPage - Litigation Strategy Planner
 *
 * Full domain-specific implementation for strategy trees, scenario modeling,
 * and evidence-to-objective mapping.
 */

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';
import type { PlaybookListItem, ItemStatus } from './types';

// ============================================
// Types & Constants
// ============================================

type Priority = 'critical' | 'high' | 'medium' | 'low';

interface StrategyMetadata {
  priority?: Priority;
  status?: ItemStatus;
  claims?: Array<{
    id: string;
    label: string;
    detail?: string;
    fallback?: string;
    children?: Array<{
      id: string;
      label: string;
      detail?: string;
    }>;
  }>;
  scenarios?: Array<{
    id: string;
    title: string;
    chain: string[];
    prediction: string;
  }>;
  evidence_mapping?: Array<{
    goal_id: string;
    evidence_ids: string[];
  }>;
}

const PRIORITY_COLORS: Record<Priority, string> = {
  critical: '#dc2626', // red
  high: '#f97316', // orange
  medium: '#3b82f6', // blue
  low: '#6b7280', // grey
};

const STATUS_COLORS: Record<ItemStatus, string> = {
  active: '#16a34a',
  archived: '#6b7280',
  deleted: '#dc2626',
};

// ============================================
// Main Page Component
// ============================================

export function PlaybookPage() {
  const [searchParams] = useSearchParams();
  const itemId = searchParams.get('itemId');

  if (!!itemId && itemId !== '') {
    return <StrategyDetailView itemId={itemId} />;
  }

  return <StrategyListView />;
}

// ============================================
// List View — Strategy Cards
// ============================================

function StrategyListView() {
  const { toast } = useToast();
  const [items, setItems] = useState<PlaybookListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();

  const loadItems = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listItems();
      setItems(data.items as unknown as PlaybookListItem[]);
    } catch (err) {
      toast.error(`Failed to load strategies: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const handleSelect = (id: string) => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set('itemId', id);
    setSearchParams(newParams);
  };

  if (loading) {
    return <LoadingSkeleton />;
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '32px',
        }}
      >
        <div>
          <h1
            style={{
              fontSize: '28px',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              margin: 0,
            }}
          >
            <Icon name="Target" size={32} /> Litigation Playbook
          </h1>
          <p
            style={{
              color: 'var(--arkham-text-muted, #6b7280)',
              marginTop: '8px',
              fontSize: '16px',
            }}
          >
            Map legal claims, model scenarios, and align evidence to strategic objectives
          </p>
        </div>
        <button
          onClick={() => setShowCreateDialog(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '10px 20px',
            background: '#3b82f6',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            cursor: 'pointer',
            fontWeight: 600,
            transition: 'background 0.2s',
          }}
        >
          <Icon name="Plus" size={20} /> New Strategy
        </button>
      </div>

      {/* Grid */}
      {items.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: '64px',
            background: 'var(--arkham-bg-secondary, #f9fafb)',
            borderRadius: '12px',
            border: '2px dashed var(--arkham-border, #e5e7eb)',
          }}
        >
          <Icon name="Target" size={64} style={{ color: '#d1d5db', marginBottom: '16px' }} />
          <h3 style={{ margin: '0 0 8px 0', fontSize: '18px' }}>No strategies defined</h3>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', margin: 0 }}>
            Start by creating your first litigation strategy plan.
          </p>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))',
            gap: '20px',
          }}
        >
          {items.map((item) => {
            const metadata = ((item as any).metadata as StrategyMetadata) || {};
            const priority = metadata.priority || 'medium';
            const status = item.status || 'active';

            return (
              <div
                key={item.id}
                onClick={() => handleSelect(item.id)}
                style={{
                  background: 'var(--arkham-bg-secondary, white)',
                  border: '1px solid var(--arkham-border, #e5e7eb)',
                  borderRadius: '12px',
                  padding: '20px',
                  cursor: 'pointer',
                  transition: 'transform 0.2s, box-shadow 0.2s',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                  position: 'relative',
                  overflow: 'hidden',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.transform = 'translateY(-4px)';
                  e.currentTarget.style.boxShadow = '0 10px 15px -3px rgba(0, 0, 0, 0.1)';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                <div
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '4px',
                    height: '100%',
                    background: PRIORITY_COLORS[priority],
                  }}
                />

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                  }}
                >
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: '12px',
                        fontSize: '11px',
                        fontWeight: 700,
                        background: `${PRIORITY_COLORS[priority]}15`,
                        color: PRIORITY_COLORS[priority],
                        textTransform: 'uppercase',
                      }}
                    >
                      {priority}
                    </span>
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: '12px',
                        fontSize: '11px',
                        fontWeight: 700,
                        background: `${STATUS_COLORS[status]}15`,
                        color: STATUS_COLORS[status],
                        textTransform: 'uppercase',
                      }}
                    >
                      {status}
                    </span>
                  </div>
                  <Icon name="ChevronRight" size={18} style={{ color: '#d1d5db' }} />
                </div>

                <div>
                  <h3 style={{ margin: '0 0 4px 0', fontSize: '18px', fontWeight: 600 }}>
                    {String(item.title)}
                  </h3>
                  <p
                    style={{
                      margin: 0,
                      color: 'var(--arkham-text-muted, #6b7280)',
                      fontSize: '14px',
                      lineHeight: 1.5,
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                  >
                    {String(item.description || 'No description provided.')}
                  </p>
                </div>

                <div
                  style={{
                    marginTop: 'auto',
                    display: 'flex',
                    gap: '16px',
                    borderTop: '1px solid var(--arkham-border, #f3f4f6)',
                    paddingTop: '12px',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '12px',
                      color: '#9ca3af',
                    }}
                  >
                    <Icon name="GitBranch" size={14} />
                    {metadata.claims?.length || 0} Claims
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '12px',
                      color: '#9ca3af',
                    }}
                  >
                    <Icon name="Zap" size={14} />
                    {metadata.scenarios?.length || 0} Scenarios
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '12px',
                      color: '#9ca3af',
                      marginLeft: 'auto',
                    }}
                  >
                    <Icon name="Clock" size={14} />
                    {new Date(item.updated_at).toLocaleDateString()}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Dialog */}
      {!!showCreateDialog && (
        <CreateStrategyDialog
          onClose={() => setShowCreateDialog(false)}
          onCreated={() => {
            setShowCreateDialog(false);
            loadItems();
          }}
        />
      )}
    </div>
  );
}

// ============================================
// Create Dialog
// ============================================

function CreateStrategyDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const { toast } = useToast();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<Priority>('medium');
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    if (!title.trim()) {
      toast.error('Title is required');
      return;
    }
    try {
      setSaving(true);
      await api.createItem({
        title: title.trim(),
        description: description.trim(),
        metadata: {
          priority,
          status: 'active',
          claims: [],
          scenarios: [],
          evidence_mapping: [],
        },
      });
      toast.success('Strategy created');
      onCreated();
    } catch (err) {
      toast.error(`Failed to create: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--arkham-bg-primary, white)',
          borderRadius: '16px',
          padding: '32px',
          width: '520px',
          maxWidth: '95vw',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          border: '1px solid var(--arkham-border, #e5e7eb)',
        }}
      >
        <h2
          style={{
            margin: '0 0 24px 0',
            fontSize: '22px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <Icon name="Target" size={24} style={{ color: '#3b82f6' }} /> Create Litigation Strategy
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <label>
            <span
              style={{ fontSize: '14px', fontWeight: 600, display: 'block', marginBottom: '8px' }}
            >
              Strategy Title
            </span>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Unfair Dismissal Claim — Q1 2024"
              style={{
                width: '100%',
                padding: '12px 16px',
                borderRadius: '8px',
                border: '1px solid var(--arkham-border, #d1d5db)',
                fontSize: '15px',
                background: 'var(--arkham-bg-primary, white)',
                color: 'inherit',
                boxSizing: 'border-box',
                outlineColor: '#3b82f6',
              }}
            />
          </label>

          <label>
            <span
              style={{ fontSize: '14px', fontWeight: 600, display: 'block', marginBottom: '8px' }}
            >
              Strategic Overview
            </span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              placeholder="Describe the core objective and approach..."
              style={{
                width: '100%',
                padding: '12px 16px',
                borderRadius: '8px',
                border: '1px solid var(--arkham-border, #d1d5db)',
                fontSize: '15px',
                resize: 'none',
                background: 'var(--arkham-bg-primary, white)',
                color: 'inherit',
                boxSizing: 'border-box',
                outlineColor: '#3b82f6',
              }}
            />
          </label>

          <div>
            <span
              style={{ fontSize: '14px', fontWeight: 600, display: 'block', marginBottom: '8px' }}
            >
              Priority Level
            </span>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px' }}>
              {(['critical', 'high', 'medium', 'low'] as Priority[]).map((p) => (
                <button
                  key={p}
                  onClick={() => setPriority(p)}
                  style={{
                    padding: '10px',
                    borderRadius: '8px',
                    border: '1px solid',
                    borderColor:
                      priority === p ? PRIORITY_COLORS[p] : 'var(--arkham-border, #e5e7eb)',
                    background: priority === p ? `${PRIORITY_COLORS[p]}10` : 'transparent',
                    color:
                      priority === p ? PRIORITY_COLORS[p] : 'var(--arkham-text-muted, #6b7280)',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    textTransform: 'capitalize',
                    transition: 'all 0.2s',
                  }}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div
          style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '32px' }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              border: '1px solid var(--arkham-border, #d1d5db)',
              background: 'transparent',
              cursor: 'pointer',
              color: 'inherit',
              fontWeight: 500,
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={saving}
            style={{
              padding: '10px 24px',
              borderRadius: '8px',
              border: 'none',
              background: '#3b82f6',
              color: 'white',
              cursor: 'pointer',
              fontWeight: 600,
              opacity: saving ? 0.6 : 1,
              transition: 'background 0.2s',
            }}
          >
            {saving ? 'Creating...' : 'Initialize Strategy'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Detail View — Strategy Engine
// ============================================

function StrategyDetailView({ itemId }: { itemId: string }) {
  const { toast } = useToast();
  const [item, setItem] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'claims' | 'scenarios' | 'evidence'>('claims');
  const [, setSearchParams] = useSearchParams();

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getItem(itemId);
      setItem(data as unknown as Record<string, unknown>);
    } catch (err) {
      toast.error(`Failed to load strategy: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [itemId, toast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const goBack = () => {
    setSearchParams(new URLSearchParams());
  };

  if (loading) return <LoadingSkeleton />;
  if (!item) return <div style={{ padding: '24px' }}>Strategy not found</div>;

  const metadata = (item.metadata || {}) as StrategyMetadata;
  const priority = metadata.priority || 'medium';
  const claims = metadata.claims || [];
  const scenarios = metadata.scenarios || [];
  const evidenceMapping = metadata.evidence_mapping || [];

  const tabs = [
    { key: 'claims' as const, label: 'Strategy Tree', icon: 'GitBranch' },
    { key: 'scenarios' as const, label: `Scenarios (${scenarios.length})`, icon: 'Zap' },
    { key: 'evidence' as const, label: 'Evidence Map', icon: 'Link' },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* Breadcrumbs / Back */}
      <button
        onClick={goBack}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          background: 'none',
          border: 'none',
          padding: 0,
          color: '#3b82f6',
          cursor: 'pointer',
          fontSize: '14px',
          marginBottom: '16px',
        }}
      >
        <Icon name="ArrowLeft" size={16} /> Back to Playbook
      </button>

      {/* Header Area */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: '32px',
          padding: '24px',
          background: 'var(--arkham-bg-secondary, white)',
          borderRadius: '16px',
          border: '1px solid var(--arkham-border, #e5e7eb)',
        }}
      >
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <h1 style={{ fontSize: '28px', fontWeight: 700, margin: 0 }}>{String(item.title)}</h1>
            <span
              style={{
                padding: '4px 12px',
                borderRadius: '12px',
                fontSize: '12px',
                fontWeight: 700,
                background: `${PRIORITY_COLORS[priority]}15`,
                color: PRIORITY_COLORS[priority],
                textTransform: 'uppercase',
              }}
            >
              {priority} Priority
            </span>
          </div>
          <p
            style={{
              color: 'var(--arkham-text-muted, #6b7280)',
              fontSize: '16px',
              lineHeight: 1.6,
              maxWidth: '800px',
              margin: 0,
            }}
          >
            {String(item.description || 'No strategy overview provided.')}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: '1px solid var(--arkham-border, #d1d5db)',
              background: 'white',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '14px',
            }}
          >
            <Icon name="Edit" size={16} /> Edit
          </button>
          <button
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: '#3b82f6',
              color: 'white',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '14px',
            }}
          >
            <Icon name="Share" size={16} /> Export
          </button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          marginBottom: '24px',
          borderBottom: '1px solid var(--arkham-border, #e5e7eb)',
          paddingBottom: '1px',
        }}
      >
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '12px 24px',
              border: 'none',
              cursor: 'pointer',
              background: 'transparent',
              fontSize: '15px',
              fontWeight: activeTab === tab.key ? 700 : 500,
              color: activeTab === tab.key ? '#3b82f6' : 'var(--arkham-text-muted, #6b7280)',
              position: 'relative',
              transition: 'color 0.2s',
            }}
          >
            <Icon name={tab.icon} size={18} />
            {tab.label}
            {activeTab === tab.key && (
              <div
                style={{
                  position: 'absolute',
                  bottom: -1,
                  left: 0,
                  right: 0,
                  height: '3px',
                  background: '#3b82f6',
                  borderRadius: '3px 3px 0 0',
                }}
              />
            )}
          </button>
        ))}
      </div>

      {/* Viewport */}
      <div style={{ minHeight: '500px' }}>
        {activeTab === 'claims' && <StrategyTreePanel claims={claims} />}
        {activeTab === 'scenarios' && <ScenariosPanel scenarios={scenarios} />}
        {activeTab === 'evidence' && <EvidenceMapPanel mapping={evidenceMapping} claims={claims} />}
      </div>
    </div>
  );
}

// ============================================
// Strategy Tree Panel
// ============================================

function StrategyTreePanel({ claims }: { claims: StrategyMetadata['claims'] }) {
  if (!claims || claims.length === 0) {
    return (
      <EmptyState
        icon="GitBranch"
        title="No claim hierarchy defined"
        subtitle="Define your primary claims and secondary fallback positions to build a strategy tree."
      />
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {claims.map((claim) => (
        <div
          key={claim.id}
          style={{
            background: 'var(--arkham-bg-secondary, white)',
            borderRadius: '12px',
            border: '1px solid var(--arkham-border, #e5e7eb)',
            padding: '24px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '8px',
                background: '#fef2f2',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#dc2626',
              }}
            >
              <Icon name="Target" size={24} />
            </div>
            <div style={{ flex: 1 }}>
              <div
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              >
                <h4 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>
                  {String(claim.label)}
                </h4>
                <span
                  style={{
                    fontSize: '12px',
                    padding: '2px 8px',
                    background: '#f3f4f6',
                    borderRadius: '4px',
                    fontWeight: 600,
                  }}
                >
                  Primary Claim
                </span>
              </div>
              <p
                style={{
                  margin: '8px 0 0 0',
                  color: 'var(--arkham-text-muted, #6b7280)',
                  fontSize: '14px',
                  lineHeight: 1.5,
                }}
              >
                {String(claim.detail || 'No detailed description.')}
              </p>

              {!!claim.fallback && (
                <div
                  style={{
                    marginTop: '16px',
                    padding: '12px',
                    background: '#fffbeb',
                    borderRadius: '8px',
                    borderLeft: '4px solid #f59e0b',
                    display: 'flex',
                    gap: '10px',
                    alignItems: 'center',
                  }}
                >
                  <Icon name="ShieldAlert" size={18} style={{ color: '#d97706' }} />
                  <div style={{ fontSize: '14px' }}>
                    <strong style={{ color: '#92400e' }}>Fallback Position:</strong>{' '}
                    {String(claim.fallback)}
                  </div>
                </div>
              )}

              {!!claim.children && claim.children.length > 0 && (
                <div
                  style={{
                    marginTop: '24px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                  }}
                >
                  <div
                    style={{
                      fontSize: '12px',
                      fontWeight: 700,
                      color: '#9ca3af',
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                    }}
                  >
                    Supporting Legal Arguments
                  </div>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                      gap: '12px',
                    }}
                  >
                    {claim.children.map((child) => (
                      <div
                        key={child.id}
                        style={{
                          padding: '16px',
                          borderRadius: '8px',
                          background: '#f8fafc',
                          border: '1px solid #e2e8f0',
                          transition: 'border-color 0.2s',
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            marginBottom: '6px',
                          }}
                        >
                          <Icon name="FileText" size={14} style={{ color: '#3b82f6' }} />
                          <div style={{ fontWeight: 600, fontSize: '14px' }}>
                            {String(child.label)}
                          </div>
                        </div>
                        <div style={{ fontSize: '13px', color: '#64748b' }}>
                          {String(child.detail)}
                        </div>
                      </div>
                    ))}
                    <button
                      style={{
                        border: '1px dashed #cbd5e1',
                        borderRadius: '8px',
                        padding: '16px',
                        background: 'transparent',
                        color: '#94a3b8',
                        fontSize: '14px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '8px',
                        cursor: 'pointer',
                      }}
                    >
                      <Icon name="Plus" size={16} /> Add Argument
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================
// Scenarios Panel
// ============================================

function ScenariosPanel({ scenarios }: { scenarios: StrategyMetadata['scenarios'] }) {
  if (!scenarios || scenarios.length === 0) {
    return (
      <EmptyState
        icon="Zap"
        title="No scenarios modeled"
        subtitle="Model 'what-if' chains and outcome predictions to prepare for opposing counsel moves."
      />
    );
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))',
        gap: '20px',
      }}
    >
      {scenarios.map((scene) => (
        <div
          key={scene.id}
          style={{
            background: 'var(--arkham-bg-secondary, white)',
            borderRadius: '12px',
            border: '1px solid var(--arkham-border, #e5e7eb)',
            padding: '24px',
            display: 'flex',
            flexDirection: 'column',
            gap: '20px',
          }}
        >
          <h4 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#3b82f6' }}>
            {String(scene.title)}
          </h4>

          <div
            style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: '16px' }}
          >
            <div
              style={{
                position: 'absolute',
                top: '10px',
                bottom: '10px',
                left: '11px',
                width: '2px',
                background: '#e2e8f0',
              }}
            />
            {scene.chain.map((step, idx) => (
              <div
                key={idx}
                style={{ display: 'flex', gap: '16px', position: 'relative', zIndex: 1 }}
              >
                <div
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    background: idx === 0 ? '#3b82f6' : 'white',
                    border: '2px solid #3b82f6',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: idx === 0 ? 'white' : '#3b82f6',
                    fontSize: '11px',
                    fontWeight: 700,
                  }}
                >
                  {idx + 1}
                </div>
                <div
                  style={{
                    fontSize: '14px',
                    padding: '8px 12px',
                    background: '#f8fafc',
                    borderRadius: '8px',
                    border: '1px solid #e2e8f0',
                    flex: 1,
                  }}
                >
                  {String(step)}
                </div>
              </div>
            ))}
          </div>

          <div
            style={{
              marginTop: 'auto',
              padding: '16px',
              background: '#f0f9ff',
              borderRadius: '8px',
              border: '1px solid #bae6fd',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <Icon name="TrendingUp" size={16} style={{ color: '#0369a1' }} />
              <div
                style={{
                  fontSize: '12px',
                  fontWeight: 700,
                  color: '#0369a1',
                  textTransform: 'uppercase',
                }}
              >
                Predicted Outcome
              </div>
            </div>
            <div style={{ fontSize: '15px', fontWeight: 600, color: '#0c4a6e' }}>
              {String(scene.prediction)}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================
// Evidence Map Panel
// ============================================

function EvidenceMapPanel({
  mapping,
  claims,
}: {
  mapping: StrategyMetadata['evidence_mapping'];
  claims: StrategyMetadata['claims'];
}) {
  if (!mapping || mapping.length === 0) {
    return (
      <EmptyState
        icon="Link"
        title="No evidence mapped"
        subtitle="Connect specific pieces of evidence to your strategic objectives to visualize coverage and gaps."
      />
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {mapping.map((map, idx) => {
        const goal = claims?.find((c) => c.id === map.goal_id) || { label: 'Unknown Objective' };

        return (
          <div
            key={idx}
            style={{
              display: 'flex',
              gap: '24px',
              background: 'var(--arkham-bg-secondary, white)',
              borderRadius: '12px',
              border: '1px solid var(--arkham-border, #e5e7eb)',
              padding: '20px',
            }}
          >
            <div style={{ width: '300px', flexShrink: 0 }}>
              <div
                style={{
                  fontSize: '12px',
                  fontWeight: 700,
                  color: '#9ca3af',
                  textTransform: 'uppercase',
                  marginBottom: '8px',
                }}
              >
                Objective
              </div>
              <div style={{ fontWeight: 600, fontSize: '16px', color: '#1e293b' }}>
                {String(goal.label)}
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', color: '#cbd5e1' }}>
              <Icon name="ArrowRight" size={24} />
            </div>

            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontSize: '12px',
                  fontWeight: 700,
                  color: '#9ca3af',
                  textTransform: 'uppercase',
                  marginBottom: '8px',
                }}
              >
                Mapped Evidence Items
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {map.evidence_ids.map((eid, eidx) => (
                  <div
                    key={eidx}
                    style={{
                      padding: '6px 12px',
                      background: '#f1f5f9',
                      borderRadius: '6px',
                      border: '1px solid #e2e8f0',
                      fontSize: '13px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    <Icon name="File" size={14} style={{ color: '#64748b' }} />
                    {eid}
                  </div>
                ))}
                <button
                  style={{
                    padding: '6px 12px',
                    background: 'transparent',
                    borderRadius: '6px',
                    border: '1px dashed #cbd5e1',
                    fontSize: '13px',
                    color: '#94a3b8',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <Icon name="Plus" size={14} /> Map More
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ============================================
// UI Atoms
// ============================================

function EmptyState({ icon, title, subtitle }: { icon: string; title: string; subtitle: string }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '80px 40px',
        background: 'var(--arkham-bg-secondary, #f9fafb)',
        borderRadius: '16px',
        border: '2px dashed var(--arkham-border, #e5e7eb)',
        textAlign: 'center',
      }}
    >
      <div
        style={{
          width: '80px',
          height: '80px',
          borderRadius: '50%',
          background: 'white',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '24px',
          boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
        }}
      >
        <Icon name={icon} size={40} style={{ color: '#cbd5e1' }} />
      </div>
      <h3 style={{ margin: '0 0 8px 0', fontSize: '20px', fontWeight: 700 }}>{title}</h3>
      <p
        style={{
          margin: 0,
          color: 'var(--arkham-text-muted, #6b7280)',
          fontSize: '15px',
          maxWidth: '400px',
          lineHeight: 1.6,
        }}
      >
        {subtitle}
      </p>
      <button
        style={{
          marginTop: '24px',
          padding: '10px 20px',
          background: '#3b82f6',
          color: 'white',
          border: 'none',
          borderRadius: '8px',
          fontWeight: 600,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
        }}
      >
        <Icon name="Plus" size={18} /> Add Your First Element
      </button>
    </div>
  );
}
