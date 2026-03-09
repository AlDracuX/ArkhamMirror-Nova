/**
 * SkeletonPage - Legal Argument Builder
 *
 * Structures skeleton arguments and legal submissions in ET-compliant format.
 * Builds argument trees: claim -> legal test -> evidence -> authority.
 * Generates full submissions, skeleton arguments, and oral hearing notes.
 */

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';

import * as api from './api';
import type { SkeletonListItem, ArgumentStatus, SubmissionType } from './types';
import { ARGUMENT_STATUS_OPTIONS, SUBMISSION_TYPE_OPTIONS } from './types';

export function SkeletonPage() {
  const [searchParams] = useSearchParams();
  const itemId = searchParams.get('itemId');

  if (itemId) {
    return <SubmissionDetailView itemId={itemId} />;
  }

  return <SubmissionListView />;
}

// ============================================
// List View — Submission Cards
// ============================================

function SubmissionListView() {
  const { toast } = useToast();
  const [items, setItems] = useState<SkeletonListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<ArgumentStatus | 'all'>('all');
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const loadItems = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listItems();
      setItems(data.items);
    } catch (err) {
      toast.error(`Failed to load submissions: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const filteredItems = filterStatus === 'all'
    ? items
    : items.filter(it => it.metadata?.argument_status === filterStatus);

  const statusCounts = {
    all: items.length,
    draft: items.filter(it => it.metadata?.argument_status === 'draft').length,
    structured: items.filter(it => it.metadata?.argument_status === 'structured').length,
    final: items.filter(it => it.metadata?.argument_status === 'final').length,
  };

  if (loading) {
    return <LoadingSkeleton />;
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1200px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <Icon name="Scale" size={24} /> Skeleton Arguments
          </h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', marginTop: '4px', fontSize: '14px' }}>
            Structure legal arguments in ET-compliant format with authority citations
          </p>
        </div>
        <button
          onClick={() => setShowCreateDialog(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            padding: '8px 16px', background: '#3b82f6', color: 'white',
            border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 500,
          }}
        >
          <Icon name="Plus" size={16} /> New Submission
        </button>
      </div>

      {/* Status Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '24px' }}>
        {[
          { key: 'all' as const, label: 'Total', color: '#6b7280', icon: 'FileText' },
          { key: 'draft' as const, label: 'Draft', color: '#6b7280', icon: 'Pencil' },
          { key: 'structured' as const, label: 'Structured', color: '#d97706', icon: 'GitBranch' },
          { key: 'final' as const, label: 'Final', color: '#16a34a', icon: 'CheckCircle' },
        ].map((s) => (
          <div
            key={s.key}
            onClick={() => setFilterStatus(s.key)}
            style={{
              padding: '16px', borderRadius: '8px',
              border: `1px solid ${filterStatus === s.key ? s.color : 'var(--arkham-border, #e5e7eb)'}`,
              background: filterStatus === s.key ? `${s.color}08` : 'var(--arkham-bg-secondary, white)',
              cursor: 'pointer', transition: 'all 0.15s',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)' }}>
              <Icon name={s.icon} size={14} /> {s.label}
            </div>
            <div style={{ fontSize: '28px', fontWeight: 700, color: s.color }}>{statusCounts[s.key]}</div>
          </div>
        ))}
      </div>

      {/* Submission List */}
      {filteredItems.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
          <Icon name="Scale" size={48} />
          <p>No submissions found. Create your first skeleton argument to begin.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {filteredItems.map((item) => {
            const argStatus = ARGUMENT_STATUS_OPTIONS.find(o => o.value === item.metadata?.argument_status);
            const subType = SUBMISSION_TYPE_OPTIONS.find(o => o.value === item.metadata?.submission_type);

            return (
              <div
                key={item.id}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '14px 16px',
                  border: '1px solid var(--arkham-border, #e5e7eb)',
                  borderLeft: `4px solid ${argStatus?.color || '#6b7280'}`,
                  borderRadius: '8px',
                  background: 'var(--arkham-bg-secondary, white)',
                  cursor: 'pointer',
                }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 600 }}>{item.title}</span>
                    {item.metadata?.claim_reference && (
                      <span style={{
                        padding: '1px 6px', borderRadius: '4px', fontSize: '11px',
                        background: 'var(--arkham-bg-tertiary, #f3f4f6)', color: 'var(--arkham-text-muted, #6b7280)',
                        fontFamily: 'monospace',
                      }}>
                        {item.metadata.claim_reference}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)', marginTop: '4px' }}>
                    {item.description || 'No description'}
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  {subType && (
                    <span style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #6b7280)' }}>
                      {subType.label}
                    </span>
                  )}
                  {item.metadata?.authority_count != null && item.metadata.authority_count > 0 && (
                    <span style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #6b7280)', display: 'flex', alignItems: 'center', gap: '3px' }}>
                      <Icon name="BookMarked" size={12} /> {item.metadata.authority_count}
                    </span>
                  )}
                  {argStatus && (
                    <span style={{
                      padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 700,
                      background: `${argStatus.color}15`, color: argStatus.color,
                    }}>
                      {argStatus.label}
                    </span>
                  )}
                  <Icon name="ChevronRight" size={16} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Dialog */}
      {showCreateDialog && (
        <CreateSubmissionDialog
          onClose={() => setShowCreateDialog(false)}
          onCreated={() => { setShowCreateDialog(false); loadItems(); }}
        />
      )}
    </div>
  );
}

// ============================================
// Create Dialog
// ============================================

function CreateSubmissionDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [submissionType, setSubmissionType] = useState<SubmissionType>('skeleton');
  const [claimRef, setClaimRef] = useState('');
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    if (!title.trim()) { toast.error('Title is required'); return; }
    try {
      setSaving(true);
      await api.createItem({
        title: title.trim(),
        description: description.trim(),
        metadata: {
          argument_status: 'draft',
          submission_type: submissionType,
          claim_reference: claimRef.trim() || undefined,
        },
      });
      toast.success('Submission created');
      onCreated();
    } catch (err) {
      toast.error(`Failed to create: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }} onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--arkham-bg-primary, white)', borderRadius: '12px',
          padding: '24px', width: '480px', maxWidth: '90vw',
          border: '1px solid var(--arkham-border, #e5e7eb)',
        }}
      >
        <h2 style={{ margin: '0 0 16px 0', fontSize: '18px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Icon name="Scale" size={20} /> New Submission
        </h2>

        <label style={{ display: 'block', marginBottom: '12px' }}>
          <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Title</span>
          <input
            value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Skeleton Argument — Direct Discrimination (s.13 EA 2010)"
            style={{
              width: '100%', padding: '8px 12px', borderRadius: '6px',
              border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px',
              background: 'var(--arkham-bg-primary, white)', color: 'inherit',
              boxSizing: 'border-box',
            }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: '12px' }}>
          <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Description</span>
          <textarea
            value={description} onChange={(e) => setDescription(e.target.value)}
            rows={3} placeholder="Brief summary of the argument..."
            style={{
              width: '100%', padding: '8px 12px', borderRadius: '6px',
              border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px', resize: 'vertical',
              background: 'var(--arkham-bg-primary, white)', color: 'inherit',
              boxSizing: 'border-box',
            }}
          />
        </label>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
          <label>
            <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Type</span>
            <select
              value={submissionType} onChange={(e) => setSubmissionType(e.target.value as SubmissionType)}
              style={{
                width: '100%', padding: '8px 12px', borderRadius: '6px',
                border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px',
                background: 'var(--arkham-bg-primary, white)', color: 'inherit',
              }}
            >
              {SUBMISSION_TYPE_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>

          <label>
            <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Claim Reference</span>
            <input
              value={claimRef} onChange={(e) => setClaimRef(e.target.value)}
              placeholder="e.g. s.13 EA 2010"
              style={{
                width: '100%', padding: '8px 12px', borderRadius: '6px',
                border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px',
                background: 'var(--arkham-bg-primary, white)', color: 'inherit',
                boxSizing: 'border-box',
              }}
            />
          </label>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button onClick={onClose} style={{
            padding: '8px 16px', borderRadius: '6px', border: '1px solid var(--arkham-border, #d1d5db)',
            background: 'transparent', cursor: 'pointer', color: 'inherit',
          }}>
            Cancel
          </button>
          <button onClick={handleCreate} disabled={saving} style={{
            padding: '8px 16px', borderRadius: '6px', border: 'none',
            background: '#3b82f6', color: 'white', cursor: 'pointer', fontWeight: 500,
            opacity: saving ? 0.6 : 1,
          }}>
            {saving ? 'Creating...' : 'Create Submission'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Detail View — Argument Tree + Authorities
// ============================================

function SubmissionDetailView({ itemId }: { itemId: string }) {
  const { toast } = useToast();
  const [item, setItem] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'tree' | 'authorities' | 'preview'>('tree');

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const data = await api.getItem(itemId);
        setItem(data as unknown as Record<string, unknown>);
      } catch (err) {
        toast.error(`Failed to load submission: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [itemId, toast]);

  if (loading) return <LoadingSkeleton />;
  if (!item) return <div style={{ padding: '24px' }}>Submission not found</div>;

  const metadata = (item.metadata || {}) as Record<string, unknown>;
  const argStatus = ARGUMENT_STATUS_OPTIONS.find(o => o.value === metadata.argument_status);
  const subType = SUBMISSION_TYPE_OPTIONS.find(o => o.value === metadata.submission_type);
  const authorities = (metadata.authorities || []) as Array<Record<string, unknown>>;
  const argumentTree = (metadata.argument_tree || []) as Array<Record<string, unknown>>;

  const tabs = [
    { key: 'tree' as const, label: 'Argument Tree', icon: 'GitBranch' },
    { key: 'authorities' as const, label: `Authorities (${authorities.length})`, icon: 'BookMarked' },
    { key: 'preview' as const, label: 'Preview', icon: 'Eye' },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: '1200px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <a href="/skeleton" style={{ color: 'var(--arkham-text-muted, #6b7280)', textDecoration: 'none', fontSize: '13px' }}>
              Skeleton Arguments
            </a>
            <Icon name="ChevronRight" size={12} />
          </div>
          <h1 style={{ fontSize: '22px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <Icon name="Scale" size={22} /> {String(item.title)}
          </h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', marginTop: '4px', fontSize: '14px' }}>
            {String(item.description || 'No description')}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {subType && (
            <span style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #6b7280)', padding: '4px 8px', background: 'var(--arkham-bg-tertiary, #f3f4f6)', borderRadius: '4px' }}>
              {subType.label}
            </span>
          )}
          {metadata.claim_reference ? (
            <span style={{ fontSize: '12px', fontFamily: 'monospace', padding: '4px 8px', background: 'var(--arkham-bg-tertiary, #f3f4f6)', borderRadius: '4px' }}>
              {String(metadata.claim_reference)}
            </span>
          ) : null}
          {argStatus && (
            <span style={{
              padding: '4px 10px', borderRadius: '12px', fontSize: '12px', fontWeight: 700,
              background: `${argStatus.color}15`, color: argStatus.color,
            }}>
              {argStatus.label}
            </span>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '2px', borderBottom: '1px solid var(--arkham-border, #e5e7eb)', marginBottom: '20px' }}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '10px 16px', border: 'none', cursor: 'pointer',
              background: 'transparent', fontSize: '14px', fontWeight: activeTab === tab.key ? 600 : 400,
              color: activeTab === tab.key ? '#3b82f6' : 'var(--arkham-text-muted, #6b7280)',
              borderBottom: activeTab === tab.key ? '2px solid #3b82f6' : '2px solid transparent',
              marginBottom: '-1px',
            }}
          >
            <Icon name={tab.icon} size={14} /> {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'tree' && (
        <ArgumentTreePanel tree={argumentTree} />
      )}
      {activeTab === 'authorities' && (
        <AuthoritiesPanel authorities={authorities} />
      )}
      {activeTab === 'preview' && (
        <PreviewPanel item={item} metadata={metadata} authorities={authorities} tree={argumentTree} />
      )}
    </div>
  );
}

// ============================================
// Argument Tree Panel
// ============================================

function ArgumentTreePanel({ tree }: { tree: Array<Record<string, unknown>> }) {
  if (tree.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        <Icon name="GitBranch" size={48} />
        <p style={{ marginTop: '12px' }}>No argument tree built yet.</p>
        <p style={{ fontSize: '13px' }}>Structure your argument as: Claim &rarr; Legal Test &rarr; Evidence &rarr; Authority</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {tree.map((node, i) => (
        <TreeNode key={String(node.id || i)} node={node} depth={0} />
      ))}
    </div>
  );
}

const NODE_TYPE_STYLES: Record<string, { color: string; icon: string; bg: string }> = {
  claim: { color: '#dc2626', icon: 'Target', bg: '#fef2f2' },
  legal_test: { color: '#7c3aed', icon: 'Scale', bg: '#faf5ff' },
  evidence: { color: '#2563eb', icon: 'FileText', bg: '#eff6ff' },
  authority: { color: '#059669', icon: 'BookMarked', bg: '#ecfdf5' },
};

function TreeNode({ node, depth }: { node: Record<string, unknown>; depth: number }) {
  const type = String(node.type || 'claim');
  const style = NODE_TYPE_STYLES[type] || NODE_TYPE_STYLES.claim;
  const children = (node.children || []) as Array<Record<string, unknown>>;

  return (
    <div style={{ marginLeft: depth * 24 }}>
      <div style={{
        padding: '10px 14px', borderRadius: '6px',
        border: `1px solid ${style.color}30`, background: style.bg,
        borderLeft: `3px solid ${style.color}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Icon name={style.icon} size={14} />
          <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: style.color }}>
            {type.replace('_', ' ')}
          </span>
        </div>
        <div style={{ fontWeight: 600, marginTop: '4px' }}>{String(node.label || '')}</div>
        {node.detail ? (
          <div style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)', marginTop: '2px' }}>
            {String(node.detail)}
          </div>
        ) : null}
        {node.bundle_refs ? (
          <div style={{ fontSize: '11px', color: 'var(--arkham-text-muted, #9ca3af)', marginTop: '4px', fontFamily: 'monospace' }}>
            Bundle: {(node.bundle_refs as string[]).join(', ')}
          </div>
        ) : null}
      </div>
      {children.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
          {children.map((child, i) => (
            <TreeNode key={String(child.id || i)} node={child} depth={depth + 1} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

// ============================================
// Authorities Panel
// ============================================

function AuthoritiesPanel({ authorities }: { authorities: Array<Record<string, unknown>> }) {
  const BINDING_COLORS: Record<string, string> = {
    binding: '#dc2626',
    persuasive: '#2563eb',
    obiter: '#6b7280',
  };

  if (authorities.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        <Icon name="BookMarked" size={48} />
        <p style={{ marginTop: '12px' }}>No authorities cited yet.</p>
        <p style={{ fontSize: '13px' }}>Add case law references to support your argument elements.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {authorities.map((auth, i) => {
        const level = String(auth.binding_level || 'persuasive');
        const color = BINDING_COLORS[level] || BINDING_COLORS.persuasive;

        return (
          <div
            key={i}
            style={{
              padding: '14px 16px', borderRadius: '8px',
              border: '1px solid var(--arkham-border, #e5e7eb)',
              borderLeft: `4px solid ${color}`,
              background: 'var(--arkham-bg-secondary, white)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ fontWeight: 600, fontStyle: 'italic' }}>{String(auth.case_name || '')}</div>
                <div style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)', fontFamily: 'monospace', marginTop: '2px' }}>
                  {String(auth.citation || '')}
                  {auth.year ? ` (${String(auth.year)})` : null}
                </div>
              </div>
              <span style={{
                padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 700,
                background: `${color}15`, color,
                textTransform: 'uppercase',
              }}>
                {level}
              </span>
            </div>
            {auth.court ? (
              <div style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)', marginTop: '4px' }}>
                {String(auth.court)}
              </div>
            ) : null}
            {auth.ratio ? (
              <div style={{
                fontSize: '13px', marginTop: '8px', padding: '8px 12px',
                background: 'var(--arkham-bg-tertiary, #f9fafb)', borderRadius: '4px',
                borderLeft: '2px solid var(--arkham-border, #d1d5db)',
              }}>
                <strong style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--arkham-text-muted, #6b7280)' }}>
                  Ratio Decidendi:
                </strong>{' '}
                {String(auth.ratio)}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

// ============================================
// Preview Panel
// ============================================

function PreviewPanel({
  item, metadata, authorities, tree,
}: {
  item: Record<string, unknown>;
  metadata: Record<string, unknown>;
  authorities: Array<Record<string, unknown>>;
  tree: Array<Record<string, unknown>>;
}) {
  return (
    <div style={{
      padding: '24px', borderRadius: '8px',
      border: '1px solid var(--arkham-border, #e5e7eb)',
      background: 'var(--arkham-bg-secondary, white)',
      fontFamily: "'Times New Roman', serif", lineHeight: 1.8,
    }}>
      <div style={{ textAlign: 'center', marginBottom: '24px' }}>
        <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '2px', color: 'var(--arkham-text-muted, #6b7280)' }}>
          In the Employment Tribunal
        </div>
        <h2 style={{ fontSize: '18px', margin: '8px 0 4px 0' }}>{String(item.title)}</h2>
        {metadata.claim_reference ? (
          <div style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)' }}>
            Re: {String(metadata.claim_reference)}
          </div>
        ) : null}
      </div>

      {tree.length === 0 && authorities.length === 0 ? (
        <div style={{ textAlign: 'center', color: 'var(--arkham-text-muted, #6b7280)', padding: '24px', fontFamily: 'inherit' }}>
          Add argument tree elements and authorities to see a formatted preview.
        </div>
      ) : (
        <>
          {tree.length > 0 && (
            <div style={{ marginBottom: '24px' }}>
              <h3 style={{ fontSize: '14px', borderBottom: '1px solid var(--arkham-border, #e5e7eb)', paddingBottom: '4px' }}>
                Argument Structure
              </h3>
              {tree.map((node, i) => (
                <div key={i} style={{ marginBottom: '8px' }}>
                  <div style={{ fontWeight: 600 }}>{i + 1}. {String(node.label || '')}</div>
                  {node.detail ? <div style={{ paddingLeft: '16px', fontSize: '14px' }}>{String(node.detail)}</div> : null}
                </div>
              ))}
            </div>
          )}

          {authorities.length > 0 && (
            <div>
              <h3 style={{ fontSize: '14px', borderBottom: '1px solid var(--arkham-border, #e5e7eb)', paddingBottom: '4px' }}>
                Authorities Cited
              </h3>
              {authorities.map((auth, i) => (
                <div key={i} style={{ marginBottom: '4px', fontSize: '14px' }}>
                  [{i + 1}] <em>{String(auth.case_name || '')}</em> {String(auth.citation || '')}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
