/**
 * RulesPage - Procedural Rules Engine
 *
 * Encodes Employment Tribunal Rules of Procedure, Practice Directions,
 * and key case management principles. Auto-calculates deadlines,
 * validates compliance, and detects respondent breaches.
 */

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';

import * as api from './api';
import type { RulesListItem, RuleCategory } from './types';
import { CATEGORY_OPTIONS, SEVERITY_OPTIONS } from './types';

type TabKey = 'catalog' | 'calculations' | 'breaches' | 'compliance';

export function RulesPage() {
  const [searchParams] = useSearchParams();
  const itemId = searchParams.get('itemId');

  if (itemId) {
    return <RuleDetailView itemId={itemId} />;
  }

  return <RulesListView />;
}

// ============================================
// Tabbed List View
// ============================================

function RulesListView() {
  const { toast } = useToast();
  const [items, setItems] = useState<RulesListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>('catalog');
  const [filterCategory, setFilterCategory] = useState<RuleCategory | 'all'>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const loadItems = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listItems();
      setItems(data.items);
    } catch (err) {
      toast.error(`Failed to load rules: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const filteredItems = items.filter(it => {
    if (filterCategory !== 'all' && it.metadata?.category !== filterCategory) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      return (
        it.title.toLowerCase().includes(q) ||
        it.description.toLowerCase().includes(q) ||
        (it.metadata?.rule_number || '').toLowerCase().includes(q) ||
        (it.metadata?.statutory_reference || '').toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Category distribution for summary
  const categoryCounts = CATEGORY_OPTIONS.map(cat => ({
    ...cat,
    count: items.filter(it => it.metadata?.category === cat.value).length,
  }));

  const tabs: { key: TabKey; label: string; icon: string }[] = [
    { key: 'catalog', label: 'Rules Catalog', icon: 'BookOpen' },
    { key: 'calculations', label: 'Deadline Calculations', icon: 'Calculator' },
    { key: 'breaches', label: 'Breaches', icon: 'AlertTriangle' },
    { key: 'compliance', label: 'Compliance Checks', icon: 'CheckCircle' },
  ];

  if (loading) return <LoadingSkeleton />;

  return (
    <div style={{ padding: '24px', maxWidth: '1200px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <Icon name="BookOpen" size={24} /> Procedural Rules
          </h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', marginTop: '4px', fontSize: '14px' }}>
            ET Rules of Procedure, deadline calculations, and compliance tracking
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
          <Icon name="Plus" size={16} /> Add Rule
        </button>
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
              background: 'transparent', fontSize: '14px',
              fontWeight: activeTab === tab.key ? 600 : 400,
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
      {activeTab === 'catalog' && (
        <>
          {/* Category pills + search */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
            <button
              onClick={() => setFilterCategory('all')}
              style={{
                padding: '4px 12px', borderRadius: '16px', fontSize: '12px', fontWeight: 500,
                border: `1px solid ${filterCategory === 'all' ? '#3b82f6' : 'var(--arkham-border, #d1d5db)'}`,
                background: filterCategory === 'all' ? '#3b82f610' : 'transparent',
                color: filterCategory === 'all' ? '#3b82f6' : 'var(--arkham-text-muted, #6b7280)',
                cursor: 'pointer',
              }}
            >
              All ({items.length})
            </button>
            {categoryCounts.filter(c => c.count > 0).map((cat) => (
              <button
                key={cat.value}
                onClick={() => setFilterCategory(cat.value)}
                style={{
                  padding: '4px 12px', borderRadius: '16px', fontSize: '12px', fontWeight: 500,
                  border: `1px solid ${filterCategory === cat.value ? cat.color : 'var(--arkham-border, #d1d5db)'}`,
                  background: filterCategory === cat.value ? `${cat.color}10` : 'transparent',
                  color: filterCategory === cat.value ? cat.color : 'var(--arkham-text-muted, #6b7280)',
                  cursor: 'pointer',
                }}
              >
                {cat.label} ({cat.count})
              </button>
            ))}
            <div style={{ flex: 1 }} />
            <input
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search rules..."
              style={{
                padding: '6px 12px', borderRadius: '6px', fontSize: '13px', width: '220px',
                border: '1px solid var(--arkham-border, #d1d5db)',
                background: 'var(--arkham-bg-primary, white)', color: 'inherit',
              }}
            />
          </div>

          {/* Rules list */}
          {filteredItems.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
              <Icon name="BookOpen" size={48} />
              <p>{searchTerm || filterCategory !== 'all' ? 'No rules match your filters.' : 'No rules yet. Add ET Rules of Procedure to get started.'}</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {filteredItems.map((item) => {
                const cat = CATEGORY_OPTIONS.find(c => c.value === item.metadata?.category);
                return (
                  <div
                    key={item.id}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '12px 16px', borderRadius: '8px',
                      border: '1px solid var(--arkham-border, #e5e7eb)',
                      borderLeft: `4px solid ${cat?.color || '#6b7280'}`,
                      background: 'var(--arkham-bg-secondary, white)',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {item.metadata?.rule_number && (
                          <span style={{
                            fontFamily: 'monospace', fontSize: '12px', fontWeight: 700,
                            padding: '1px 6px', borderRadius: '4px',
                            background: `${cat?.color || '#6b7280'}15`, color: cat?.color || '#6b7280',
                          }}>
                            r.{item.metadata.rule_number}
                          </span>
                        )}
                        <span style={{ fontWeight: 600 }}>{item.title}</span>
                      </div>
                      <div style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)', marginTop: '3px' }}>
                        {item.description || 'No description'}
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      {item.metadata?.statutory_reference && (
                        <span style={{ fontSize: '11px', color: 'var(--arkham-text-muted, #9ca3af)', fontFamily: 'monospace' }}>
                          {item.metadata.statutory_reference}
                        </span>
                      )}
                      {cat && (
                        <span style={{
                          padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 600,
                          background: `${cat.color}12`, color: cat.color,
                        }}>
                          {cat.label}
                        </span>
                      )}
                      <Icon name="ChevronRight" size={16} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {activeTab === 'calculations' && <DeadlineCalculationsTab />}
      {activeTab === 'breaches' && <BreachesTab />}
      {activeTab === 'compliance' && <ComplianceTab />}

      {/* Create Dialog */}
      {showCreateDialog && (
        <CreateRuleDialog
          onClose={() => setShowCreateDialog(false)}
          onCreated={() => { setShowCreateDialog(false); loadItems(); }}
        />
      )}
    </div>
  );
}

// ============================================
// Deadline Calculations Tab (placeholder data-driven)
// ============================================

function DeadlineCalculationsTab() {
  return (
    <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
      <Icon name="Calculator" size={48} />
      <p style={{ marginTop: '12px', fontWeight: 500 }}>Deadline Calculations</p>
      <p style={{ fontSize: '13px' }}>
        Auto-calculate deadlines from trigger events (e.g. &quot;14 days from date of order&quot;).
        <br />Connect rules with deadline formulas to the Deadlines shard for live tracking.
      </p>
    </div>
  );
}

// ============================================
// Breaches Tab
// ============================================

function BreachesTab() {
  return (
    <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
      <Icon name="AlertTriangle" size={48} />
      <p style={{ marginTop: '12px', fontWeight: 500 }}>Respondent Breaches</p>
      <p style={{ fontSize: '13px' }}>
        Log instances where respondents breach procedural rules.
        <br />Auto-generates applications for strike-out or unless orders.
      </p>
      <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '16px' }}>
        {SEVERITY_OPTIONS.map(s => (
          <span key={s.value} style={{
            padding: '4px 10px', borderRadius: '12px', fontSize: '11px', fontWeight: 600,
            background: `${s.color}12`, color: s.color,
          }}>
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}

// ============================================
// Compliance Tab
// ============================================

function ComplianceTab() {
  return (
    <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
      <Icon name="CheckCircle" size={48} />
      <p style={{ marginTop: '12px', fontWeight: 500 }}>Compliance Checks</p>
      <p style={{ fontSize: '13px' }}>
        Validate submissions for procedural compliance before filing.
        <br />Checks format, content requirements, and deadline adherence.
      </p>
    </div>
  );
}

// ============================================
// Create Dialog
// ============================================

function CreateRuleDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [ruleNumber, setRuleNumber] = useState('');
  const [category, setCategory] = useState<RuleCategory>('procedure');
  const [statutoryRef, setStatutoryRef] = useState('');
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    if (!title.trim()) { toast.error('Title is required'); return; }
    try {
      setSaving(true);
      await api.createItem({
        title: title.trim(),
        description: description.trim(),
        metadata: {
          rule_number: ruleNumber.trim() || undefined,
          category,
          statutory_reference: statutoryRef.trim() || undefined,
        },
      });
      toast.success('Rule added');
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
          <Icon name="BookOpen" size={20} /> Add Rule
        </h2>

        <label style={{ display: 'block', marginBottom: '12px' }}>
          <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Title</span>
          <input
            value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Response to ET1 Claim"
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
            rows={3} placeholder="What does this rule require?"
            style={{
              width: '100%', padding: '8px 12px', borderRadius: '6px',
              border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px', resize: 'vertical',
              background: 'var(--arkham-bg-primary, white)', color: 'inherit',
              boxSizing: 'border-box',
            }}
          />
        </label>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
          <label>
            <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Rule Number</span>
            <input
              value={ruleNumber} onChange={(e) => setRuleNumber(e.target.value)}
              placeholder="e.g. 16"
              style={{
                width: '100%', padding: '8px 12px', borderRadius: '6px',
                border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px',
                background: 'var(--arkham-bg-primary, white)', color: 'inherit',
                boxSizing: 'border-box',
              }}
            />
          </label>

          <label>
            <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Category</span>
            <select
              value={category} onChange={(e) => setCategory(e.target.value as RuleCategory)}
              style={{
                width: '100%', padding: '8px 12px', borderRadius: '6px',
                border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px',
                background: 'var(--arkham-bg-primary, white)', color: 'inherit',
              }}
            >
              {CATEGORY_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
        </div>

        <label style={{ display: 'block', marginBottom: '16px' }}>
          <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Statutory Reference</span>
          <input
            value={statutoryRef} onChange={(e) => setStatutoryRef(e.target.value)}
            placeholder="e.g. ET Rules 2013, Schedule 1"
            style={{
              width: '100%', padding: '8px 12px', borderRadius: '6px',
              border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px',
              background: 'var(--arkham-bg-primary, white)', color: 'inherit',
              boxSizing: 'border-box',
            }}
          />
        </label>

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
            {saving ? 'Adding...' : 'Add Rule'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Detail View
// ============================================

function RuleDetailView({ itemId }: { itemId: string }) {
  const { toast } = useToast();
  const [item, setItem] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const data = await api.getItem(itemId);
        setItem(data as unknown as Record<string, unknown>);
      } catch (err) {
        toast.error(`Failed to load rule: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [itemId, toast]);

  if (loading) return <LoadingSkeleton />;
  if (!item) return <div style={{ padding: '24px' }}>Rule not found</div>;

  const metadata = (item.metadata || {}) as Record<string, unknown>;
  const cat = CATEGORY_OPTIONS.find(c => c.value === metadata.category);

  return (
    <div style={{ padding: '24px', maxWidth: '900px' }}>
      {/* Breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <a href="/rules" style={{ color: 'var(--arkham-text-muted, #6b7280)', textDecoration: 'none', fontSize: '13px' }}>
          Rules
        </a>
        <Icon name="ChevronRight" size={12} />
      </div>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
        <Icon name="BookOpen" size={22} />
        {!!metadata.rule_number && (
          <span style={{
            fontFamily: 'monospace', fontSize: '14px', fontWeight: 700,
            padding: '2px 8px', borderRadius: '4px',
            background: `${cat?.color || '#6b7280'}15`, color: cat?.color || '#6b7280',
          }}>
            r.{String(metadata.rule_number)}
          </span>
        )}
        <h1 style={{ margin: 0, fontSize: '22px', fontWeight: 600 }}>{String(item.title)}</h1>
      </div>

      {/* Meta tags */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' }}>
        {cat && (
          <span style={{
            padding: '3px 10px', borderRadius: '12px', fontSize: '12px', fontWeight: 600,
            background: `${cat.color}12`, color: cat.color,
          }}>
            {cat.label}
          </span>
        )}
        {!!metadata.statutory_reference && (
          <span style={{
            padding: '3px 10px', borderRadius: '12px', fontSize: '12px',
            background: 'var(--arkham-bg-tertiary, #f3f4f6)', color: 'var(--arkham-text-muted, #6b7280)',
            fontFamily: 'monospace',
          }}>
            {String(metadata.statutory_reference)}
          </span>
        )}
        {!!metadata.source && (
          <span style={{
            padding: '3px 10px', borderRadius: '12px', fontSize: '12px',
            background: 'var(--arkham-bg-tertiary, #f3f4f6)', color: 'var(--arkham-text-muted, #6b7280)',
          }}>
            {String(metadata.source)}
          </span>
        )}
      </div>

      {/* Body */}
      <div style={{
        padding: '20px', borderRadius: '8px',
        border: '1px solid var(--arkham-border, #e5e7eb)',
        background: 'var(--arkham-bg-secondary, white)',
        lineHeight: 1.7,
      }}>
        <p style={{ margin: 0 }}>{String(item.description || 'No description provided.')}</p>

        {!!metadata.deadline_formula && (
          <div style={{
            marginTop: '16px', padding: '12px', borderRadius: '6px',
            background: 'var(--arkham-bg-tertiary, #f9fafb)',
            borderLeft: '3px solid #3b82f6',
          }}>
            <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: '#3b82f6', marginBottom: '4px' }}>
              Deadline Formula
            </div>
            <div style={{ fontFamily: 'monospace', fontSize: '14px' }}>{String(metadata.deadline_formula)}</div>
          </div>
        )}

        {!!metadata.notes && (
          <div style={{
            marginTop: '16px', padding: '12px', borderRadius: '6px',
            background: 'var(--arkham-bg-tertiary, #f9fafb)',
            borderLeft: '3px solid #d97706',
          }}>
            <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: '#d97706', marginBottom: '4px' }}>
              Notes
            </div>
            <div style={{ fontSize: '14px' }}>{String(metadata.notes)}</div>
          </div>
        )}
      </div>
    </div>
  );
}
