/**
 * CostsPage - Costs & Wasted Costs Tracker
 *
 * Tracks time spent, expenses, and respondent conduct for potential costs applications.
 * Logs every instance of respondent delay, evasion, or vexatious behavior.
 * Auto-generates Schedule of Costs and costs applications citing specific conduct.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';

import * as api from './api';
import type { CostsListItem, CostEntryType, ConductCategory } from './types';
import { ENTRY_TYPE_OPTIONS, CONDUCT_OPTIONS, APPLICATION_STATUS_OPTIONS } from './types';

type TabKey = 'time' | 'expenses' | 'conduct' | 'applications';

export function CostsPage() {
  const [searchParams] = useSearchParams();
  const itemId = searchParams.get('itemId');

  if (itemId) {
    return <CostDetailView itemId={itemId} />;
  }

  return <CostsListView />;
}

// ============================================
// Tabbed List View
// ============================================

function CostsListView() {
  const { toast } = useToast();
  const [items, setItems] = useState<CostsListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>('time');
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const loadItems = useCallback(async () => {
    try {
      setLoading(true);
      const [timeEntries, expenses, conductLog, applications] = await Promise.all([
        api.listTimeEntries().catch(() => [] as Record<string, unknown>[]),
        api.listExpenses().catch(() => [] as Record<string, unknown>[]),
        api.listConductLog().catch(() => [] as Record<string, unknown>[]),
        api.listApplications().catch(() => [] as Record<string, unknown>[]),
      ]);

      const mapped: CostsListItem[] = [
        ...timeEntries.map((e) => ({
          id: String(e.id),
          title: String(e.activity || ''),
          description: String(e.notes || ''),
          status: 'active' as const,
          created_at: String(e.created_at || e.activity_date || ''),
          updated_at: String(e.updated_at || e.created_at || ''),
          metadata: {
            entry_type: 'time' as CostEntryType,
            hours: typeof e.duration_minutes === 'number' ? e.duration_minutes / 60 : undefined,
          },
        })),
        ...expenses.map((e) => ({
          id: String(e.id),
          title: String(e.description || ''),
          description: '',
          status: 'active' as const,
          created_at: String(e.created_at || e.expense_date || ''),
          updated_at: String(e.updated_at || e.created_at || ''),
          metadata: {
            entry_type: 'expense' as CostEntryType,
            amount: typeof e.amount === 'number' ? e.amount : undefined,
          },
        })),
        ...conductLog.map((e) => ({
          id: String(e.id),
          title: `${String(e.party_name || '')} — ${String(e.conduct_type || '')}`,
          description: String(e.description || ''),
          status: 'active' as const,
          created_at: String(e.created_at || e.occurred_at || ''),
          updated_at: String(e.updated_at || e.created_at || ''),
          metadata: {
            entry_type: 'conduct' as CostEntryType,
            conduct_category: e.conduct_type as ConductCategory | undefined,
            respondent: typeof e.party_name === 'string' ? e.party_name : undefined,
          },
        })),
        ...applications.map((e) => ({
          id: String(e.id),
          title: String(e.title || e.description || 'Application'),
          description: '',
          status: 'active' as const,
          created_at: String(e.created_at || ''),
          updated_at: String(e.updated_at || e.created_at || ''),
          metadata: {
            entry_type: 'application' as CostEntryType,
          },
        })),
      ];

      setItems(mapped);
    } catch (err) {
      toast.error(`Failed to load costs: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  // Filter items by tab's entry type
  const tabEntryType: Record<TabKey, CostEntryType> = {
    time: 'time',
    expenses: 'expense',
    conduct: 'conduct',
    applications: 'application',
  };

  const filteredItems = items.filter(
    it => it.metadata?.entry_type === tabEntryType[activeTab]
  );

  // Summary stats
  const summary = useMemo(() => {
    const timeItems = items.filter(it => it.metadata?.entry_type === 'time');
    const expenseItems = items.filter(it => it.metadata?.entry_type === 'expense');
    const conductItems = items.filter(it => it.metadata?.entry_type === 'conduct');
    const appItems = items.filter(it => it.metadata?.entry_type === 'application');

    const totalHours = timeItems.reduce((sum, it) => sum + (it.metadata?.hours || 0), 0);
    const totalExpenses = expenseItems.reduce((sum, it) => sum + (it.metadata?.amount || 0), 0);

    return {
      totalHours,
      totalExpenses,
      conductCount: conductItems.length,
      appCount: appItems.length,
      timeCount: timeItems.length,
      expenseCount: expenseItems.length,
    };
  }, [items]);

  const tabs: { key: TabKey; label: string; icon: string; count: number }[] = [
    { key: 'time', label: 'Time Entries', icon: 'Clock', count: summary.timeCount },
    { key: 'expenses', label: 'Expenses', icon: 'Receipt', count: summary.expenseCount },
    { key: 'conduct', label: 'Conduct Log', icon: 'AlertTriangle', count: summary.conductCount },
    { key: 'applications', label: 'Applications', icon: 'FileText', count: summary.appCount },
  ];

  if (loading) return <LoadingSkeleton />;

  return (
    <div style={{ padding: '24px', maxWidth: '1200px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <Icon name="PoundSterling" size={24} /> Costs Tracker
          </h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', marginTop: '4px', fontSize: '14px' }}>
            Track time, expenses, and respondent conduct for Rule 76 costs applications
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
          <Icon name="Plus" size={16} /> Add Entry
        </button>
      </div>

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '24px' }}>
        <SummaryCard
          label="Time Logged"
          value={`${summary.totalHours.toFixed(1)}h`}
          sub={`${summary.timeCount} entries`}
          color="#2563eb" icon="Clock"
        />
        <SummaryCard
          label="Expenses"
          value={`£${summary.totalExpenses.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          sub={`${summary.expenseCount} receipts`}
          color="#059669" icon="Receipt"
        />
        <SummaryCard
          label="Conduct Instances"
          value={String(summary.conductCount)}
          sub="logged for R.76"
          color="#dc2626" icon="AlertTriangle"
        />
        <SummaryCard
          label="Applications"
          value={String(summary.appCount)}
          sub="drafted / filed"
          color="#7c3aed" icon="FileText"
        />
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
            {tab.count > 0 && (
              <span style={{
                padding: '0 6px', borderRadius: '10px', fontSize: '11px', fontWeight: 600,
                background: activeTab === tab.key ? '#3b82f615' : 'var(--arkham-bg-tertiary, #f3f4f6)',
                color: activeTab === tab.key ? '#3b82f6' : 'var(--arkham-text-muted, #9ca3af)',
              }}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {filteredItems.length === 0 ? (
        <EmptyTabState tab={activeTab} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {filteredItems.map((item) => (
            <CostEntryRow key={item.id} item={item} tab={activeTab} />
          ))}
        </div>
      )}

      {/* Create Dialog */}
      {showCreateDialog && (
        <CreateCostDialog
          defaultType={tabEntryType[activeTab]}
          onClose={() => setShowCreateDialog(false)}
          onCreated={() => { setShowCreateDialog(false); loadItems(); }}
        />
      )}
    </div>
  );
}

// ============================================
// Summary Card
// ============================================

function SummaryCard({ label, value, sub, color, icon }: {
  label: string; value: string; sub: string; color: string; icon: string;
}) {
  return (
    <div style={{
      padding: '16px', borderRadius: '8px',
      border: '1px solid var(--arkham-border, #e5e7eb)',
      background: 'var(--arkham-bg-secondary, white)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        <Icon name={icon} size={14} /> {label}
      </div>
      <div style={{ fontSize: '28px', fontWeight: 700, color, marginTop: '4px' }}>{value}</div>
      <div style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)' }}>{sub}</div>
    </div>
  );
}

// ============================================
// Cost Entry Row
// ============================================

function CostEntryRow({ item, tab }: { item: CostsListItem; tab: TabKey }) {
  const formatDate = (d: string) => {
    try {
      return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch { return d; }
  };

  const entryType = ENTRY_TYPE_OPTIONS.find(e => e.value === item.metadata?.entry_type);
  const conductCat = CONDUCT_OPTIONS.find(c => c.value === item.metadata?.conduct_category);
  const appStatus = APPLICATION_STATUS_OPTIONS.find(a => a.value === item.metadata?.application_status);

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '12px 16px', borderRadius: '8px',
      border: '1px solid var(--arkham-border, #e5e7eb)',
      borderLeft: `4px solid ${entryType?.color || '#6b7280'}`,
      background: 'var(--arkham-bg-secondary, white)',
      cursor: 'pointer',
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600 }}>{item.title}</div>
        <div style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)', marginTop: '2px' }}>
          {item.description || 'No description'}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {/* Time-specific */}
        {tab === 'time' && item.metadata?.hours != null && (
          <span style={{ fontWeight: 700, fontSize: '14px', color: '#2563eb' }}>
            {item.metadata.hours}h
          </span>
        )}

        {/* Expense-specific */}
        {tab === 'expenses' && item.metadata?.amount != null && (
          <span style={{ fontWeight: 700, fontSize: '14px', color: '#059669' }}>
            £{Number(item.metadata.amount).toFixed(2)}
          </span>
        )}

        {/* Conduct-specific */}
        {tab === 'conduct' && conductCat && (
          <span style={{
            padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 700,
            background: `${conductCat.color}12`, color: conductCat.color,
          }}>
            {conductCat.label}
          </span>
        )}

        {/* Conduct respondent */}
        {tab === 'conduct' && item.metadata?.respondent && (
          <span style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #6b7280)' }}>
            {item.metadata.respondent}
          </span>
        )}

        {/* Application-specific */}
        {tab === 'applications' && appStatus && (
          <span style={{
            padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 700,
            background: `${appStatus.color}12`, color: appStatus.color,
          }}>
            {appStatus.label}
          </span>
        )}

        <span style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)' }}>
          {formatDate(item.created_at)}
        </span>

        <Icon name="ChevronRight" size={16} />
      </div>
    </div>
  );
}

// ============================================
// Empty Tab State
// ============================================

function EmptyTabState({ tab }: { tab: TabKey }) {
  const config: Record<TabKey, { icon: string; title: string; desc: string }> = {
    time: {
      icon: 'Clock',
      title: 'No time entries',
      desc: 'Log time spent on case preparation, research, and correspondence.',
    },
    expenses: {
      icon: 'Receipt',
      title: 'No expenses recorded',
      desc: 'Track printing, postage, travel, and other out-of-pocket costs.',
    },
    conduct: {
      icon: 'AlertTriangle',
      title: 'No conduct instances logged',
      desc: 'Record respondent delay, evasion, and unreasonable behaviour for R.76 threshold.',
    },
    applications: {
      icon: 'FileText',
      title: 'No costs applications',
      desc: 'Draft costs applications citing specific conduct instances and rule breaches.',
    },
  };

  const c = config[tab];

  return (
    <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
      <Icon name={c.icon} size={48} />
      <p style={{ marginTop: '12px', fontWeight: 500 }}>{c.title}</p>
      <p style={{ fontSize: '13px' }}>{c.desc}</p>
    </div>
  );
}

// ============================================
// Create Dialog
// ============================================

function CreateCostDialog({
  defaultType, onClose, onCreated,
}: {
  defaultType: CostEntryType; onClose: () => void; onCreated: () => void;
}) {
  const { toast } = useToast();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [entryType, setEntryType] = useState<CostEntryType>(defaultType);
  const [hours, setHours] = useState('');
  const [amount, setAmount] = useState('');
  const [respondent, setRespondent] = useState('');
  const [conductCategory, setConductCategory] = useState<ConductCategory>('delay');
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    if (!title.trim()) { toast.error('Title is required'); return; }
    try {
      setSaving(true);

      if (entryType === 'time') {
        await api.createTimeEntry({
          activity: title.trim(),
          duration_minutes: hours ? Math.round(parseFloat(hours) * 60) : 0,
          activity_date: new Date().toISOString().split('T')[0],
          notes: description.trim(),
        });
      } else if (entryType === 'expense') {
        await api.createExpense({
          description: title.trim(),
          amount: amount ? parseFloat(amount) : 0,
          expense_date: new Date().toISOString().split('T')[0],
        });
      } else if (entryType === 'conduct') {
        await api.createConductLog({
          party_name: respondent.trim() || 'Unknown',
          conduct_type: conductCategory,
          description: `${title.trim()}${description.trim() ? ` — ${description.trim()}` : ''}`,
          occurred_at: new Date().toISOString(),
        });
      }

      toast.success('Entry created');
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
          <Icon name="PoundSterling" size={20} /> Add Cost Entry
        </h2>

        <label style={{ display: 'block', marginBottom: '12px' }}>
          <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Entry Type</span>
          <select
            value={entryType} onChange={(e) => setEntryType(e.target.value as CostEntryType)}
            style={{
              width: '100%', padding: '8px 12px', borderRadius: '6px',
              border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px',
              background: 'var(--arkham-bg-primary, white)', color: 'inherit',
            }}
          >
            {ENTRY_TYPE_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>

        <label style={{ display: 'block', marginBottom: '12px' }}>
          <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Title</span>
          <input
            value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder={entryType === 'time' ? 'e.g. Bundle preparation' : entryType === 'expense' ? 'e.g. Court filing fee' : entryType === 'conduct' ? 'e.g. Late disclosure — 3 weeks past deadline' : 'e.g. Costs application — unreasonable conduct'}
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
            rows={2} placeholder="Details..."
            style={{
              width: '100%', padding: '8px 12px', borderRadius: '6px',
              border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px', resize: 'vertical',
              background: 'var(--arkham-bg-primary, white)', color: 'inherit',
              boxSizing: 'border-box',
            }}
          />
        </label>

        {/* Type-specific fields */}
        {entryType === 'time' && (
          <label style={{ display: 'block', marginBottom: '12px' }}>
            <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Hours</span>
            <input
              type="number" step="0.25" min="0" value={hours}
              onChange={(e) => setHours(e.target.value)}
              placeholder="e.g. 2.5"
              style={{
                width: '100%', padding: '8px 12px', borderRadius: '6px',
                border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px',
                background: 'var(--arkham-bg-primary, white)', color: 'inherit',
                boxSizing: 'border-box',
              }}
            />
          </label>
        )}

        {entryType === 'expense' && (
          <label style={{ display: 'block', marginBottom: '12px' }}>
            <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Amount (GBP)</span>
            <input
              type="number" step="0.01" min="0" value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="e.g. 45.00"
              style={{
                width: '100%', padding: '8px 12px', borderRadius: '6px',
                border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px',
                background: 'var(--arkham-bg-primary, white)', color: 'inherit',
                boxSizing: 'border-box',
              }}
            />
          </label>
        )}

        {entryType === 'conduct' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
            <label>
              <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Category</span>
              <select
                value={conductCategory} onChange={(e) => setConductCategory(e.target.value as ConductCategory)}
                style={{
                  width: '100%', padding: '8px 12px', borderRadius: '6px',
                  border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px',
                  background: 'var(--arkham-bg-primary, white)', color: 'inherit',
                }}
              >
                {CONDUCT_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </label>
            <label>
              <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Respondent</span>
              <input
                value={respondent} onChange={(e) => setRespondent(e.target.value)}
                placeholder="e.g. TLT Solicitors"
                style={{
                  width: '100%', padding: '8px 12px', borderRadius: '6px',
                  border: '1px solid var(--arkham-border, #d1d5db)', fontSize: '14px',
                  background: 'var(--arkham-bg-primary, white)', color: 'inherit',
                  boxSizing: 'border-box',
                }}
              />
            </label>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '16px' }}>
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
            {saving ? 'Adding...' : 'Add Entry'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Detail View
// ============================================

function CostDetailView({ itemId }: { itemId: string }) {
  // The costs backend does not expose a single-item GET endpoint.
  // Individual entries are viewed from the list. Show a redirect prompt.
  return (
    <div style={{ padding: '24px', maxWidth: '900px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <a href="/costs" style={{ color: 'var(--arkham-text-muted, #6b7280)', textDecoration: 'none', fontSize: '13px' }}>
          Costs
        </a>
        <Icon name="ChevronRight" size={12} />
      </div>
      <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        <Icon name="PoundSterling" size={48} />
        <p style={{ marginTop: '12px', fontWeight: 500 }}>Entry: {itemId}</p>
        <p style={{ fontSize: '13px' }}>
          Individual cost entries are displayed in the tabbed list view.
        </p>
        <a href="/costs" style={{ color: '#3b82f6', textDecoration: 'none', fontWeight: 500 }}>
          Back to Costs Tracker
        </a>
      </div>
    </div>
  );
}
