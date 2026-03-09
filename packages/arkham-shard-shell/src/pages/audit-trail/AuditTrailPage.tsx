/**
 * AuditTrailPage - Immutable Forensic Audit Log
 *
 * Provides a comprehensive, append-only chronological record of all system actions.
 * Supports forensic documentation through action logs, session tracking, and export history.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';

type TabKey = 'actions' | 'sessions' | 'exports';

interface FilterState {
  user_id: string;
  action_type: string;
  date_from: string;
  date_to: string;
}

export function AuditTrailPage() {
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  // State
  const [activeTab, setActiveTab] = useState<TabKey>((searchParams.get('tab') as TabKey) || 'actions');
  const [loading, setLoading] = useState(true);
  const [actions, setActions] = useState<Record<string, unknown>[]>([]);
  const [sessions, setSessions] = useState<Record<string, unknown>[]>([]);
  const [exports, setExports] = useState<Record<string, unknown>[]>([]);
  const [summary, setSummary] = useState<{ total_actions: number; shards: Record<string, number> }>({
    total_actions: 0,
    shards: {},
  });

  const [filters, setFilters] = useState<FilterState>({
    user_id: searchParams.get('user_id') || '',
    action_type: searchParams.get('action_type') || '',
    date_from: searchParams.get('date_from') || '',
    date_to: searchParams.get('date_to') || '',
  });

  const [showExportDialog, setShowExportDialog] = useState(false);

  useEffect(() => {
    const tab = searchParams.get('tab') as TabKey;
    if (tab && tab !== activeTab) {
      setActiveTab(tab);
    }
  }, [searchParams, activeTab]);

  const handleTabChange = (tab: TabKey) => {
    setActiveTab(tab);
    setSearchParams((prev) => {
      prev.set('tab', tab);
      return prev;
    });
  };

  const loadData = useCallback(async () => {
    try {
      setLoading(true);

      const [summaryData, actionsData, sessionsData, exportsData] = await Promise.all([
        api.getAuditSummary().catch(() => ({ total_actions: 0, shards: {} })),
        api.listActions({
          user_id: filters.user_id || undefined,
          action_type: filters.action_type || undefined,
          limit: 100,
        }).catch(() => ({ count: 0, actions: [] })),
        api.listSessions(50).catch(() => ({ count: 0, sessions: [] })),
        api.listExports(50).catch(() => ({ count: 0, exports: [] })),
      ]);

      setSummary(summaryData);
      setActions(actionsData.actions);
      setSessions(sessionsData.sessions);
      setExports(exportsData.exports);
    } catch (err) {
      toast.error(`Failed to load audit trail: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }, [filters, toast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Derived statistics
  const derivedStats = useMemo(() => {
    const uniqueUsers = new Set(actions.map(a => String(a.user_id || 'unknown')));

    let dateRange = 'N/A';
    if (actions.length > 0) {
      const dates = actions
        .map(a => new Date(String(a.created_at || a.timestamp || '')).getTime())
        .filter(t => !isNaN(t));

      if (dates.length > 0) {
        const min = new Date(Math.min(...dates));
        const max = new Date(Math.max(...dates));
        dateRange = `${min.toLocaleDateString()} - ${max.toLocaleDateString()}`;
      }
    }

    return {
      uniqueUsers: uniqueUsers.size,
      dateRange,
    };
  }, [actions]);

  if (loading && actions.length === 0) {
    return <LoadingSkeleton />;
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto', color: 'var(--arkham-text-primary, #111827)' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '32px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Icon name="ShieldCheck" size={32} color="#059669" /> System Audit Trail
          </h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', marginTop: '8px', fontSize: '15px' }}>
            Immutable append-only ledger of all system interactions and data transformations.
          </p>
        </div>
        <button
          onClick={() => setShowExportDialog(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '10px 20px', background: 'var(--arkham-bg-accent, #059669)', color: 'white',
            border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 600,
            boxShadow: '0 1px 2px rgba(0,0,0,0.05)', transition: 'background 0.2s',
          }}
        >
          <Icon name="Download" size={18} /> Record Export
        </button>
      </div>

      {/* Summary Stats Panel */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '32px' }}>
        <StatCard
          label="Total Actions"
          value={String(summary.total_actions)}
          subText="Global system-wide"
          icon="Activity"
          color="#059669"
        />
        <StatCard
          label="Unique Users"
          value={String(derivedStats.uniqueUsers)}
          subText="Active contributors"
          icon="Users"
          color="#2563eb"
        />
        <StatCard
          label="Date Range"
          value={derivedStats.dateRange}
          subText="Current viewport"
          icon="Calendar"
          color="#7c3aed"
        />
        <StatCard
          label="Active Shards"
          value={String(Object.keys(summary.shards).length)}
          subText="Reporting modules"
          icon="LayoutGrid"
          color="#ea580c"
        />
      </div>

      {/* Tabs & Filters */}
      <div style={{
        background: 'var(--arkham-bg-secondary, #ffffff)',
        borderRadius: '12px',
        border: '1px solid var(--arkham-border, #e5e7eb)',
        overflow: 'hidden',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
      }}>
        {/* Tab Header */}
        <div style={{
          display: 'flex',
          borderBottom: '1px solid var(--arkham-border, #e5e7eb)',
          background: 'var(--arkham-bg-tertiary, #f9fafb)'
        }}>
          <TabButton
            active={activeTab === 'actions'}
            onClick={() => handleTabChange('actions')}
            label="Actions"
            icon="ScrollText"
            count={actions.length}
          />
          <TabButton
            active={activeTab === 'sessions'}
            onClick={() => handleTabChange('sessions')}
            label="Sessions"
            icon="Fingerprint"
            count={sessions.length}
          />
          <TabButton
            active={activeTab === 'exports'}
            onClick={() => handleTabChange('exports')}
            label="Exports"
            icon="FileOutput"
            count={exports.length}
          />
        </div>

        {/* Filters Bar (Only for Actions tab) */}
        {activeTab === 'actions' && (
          <div style={{
            padding: '16px 24px',
            background: 'white',
            borderBottom: '1px solid var(--arkham-border, #e5e7eb)',
            display: 'flex',
            gap: '16px',
            alignItems: 'center',
            flexWrap: 'wrap'
          }}>
            <FilterField label="Action Type">
              <select
                value={filters.action_type}
                onChange={(e) => setFilters(f => ({ ...f, action_type: e.target.value }))}
                style={{
                  padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--arkham-border, #e5e7eb)',
                  fontSize: '14px', minWidth: '140px', outline: 'none', background: 'white'
                }}
              >
                {[
                  { value: '', label: 'All Types' },
                  { value: 'create', label: 'Creation' },
                  { value: 'update', label: 'Modification' },
                  { value: 'delete', label: 'Deletion' },
                  { value: 'read', label: 'Access' },
                  { value: 'export', label: 'Export' },
                ].map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </FilterField>
            <FilterField label="User ID">
              <input
                value={filters.user_id}
                onChange={(e) => setFilters(f => ({ ...f, user_id: e.target.value }))}
                placeholder="Filter by user..."
                style={{
                  padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--arkham-border, #e5e7eb)',
                  fontSize: '14px', outline: 'none', minWidth: '180px'
                }}
              />
            </FilterField>
            <FilterField label="From Date">
              <input
                type="date"
                value={filters.date_from}
                onChange={(e) => setFilters(f => ({ ...f, date_from: e.target.value }))}
                style={{
                  padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--arkham-border, #e5e7eb)',
                  fontSize: '14px', outline: 'none'
                }}
              />
            </FilterField>
            <FilterField label="To Date">
              <input
                type="date"
                value={filters.date_to}
                onChange={(e) => setFilters(f => ({ ...f, date_to: e.target.value }))}
                style={{
                  padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--arkham-border, #e5e7eb)',
                  fontSize: '14px', outline: 'none'
                }}
              />
            </FilterField>
            <button
              onClick={() => setFilters({ user_id: '', action_type: '', date_from: '', date_to: '' })}
              style={{
                marginTop: '18px',
                padding: '8px 12px',
                background: 'transparent',
                border: '1px solid var(--arkham-border, #e5e7eb)',
                borderRadius: '6px',
                fontSize: '13px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px'
              }}
            >
              <Icon name="RotateCcw" size={14} /> Reset
            </button>
          </div>
        )}

        {/* Content Area */}
        <div style={{ padding: '0' }}>
          {activeTab === 'actions' && <ActionLogTable actions={actions} />}
          {activeTab === 'sessions' && <SessionList sessions={sessions} />}
          {activeTab === 'exports' && <ExportList exports={exports} />}
        </div>
      </div>

      {/* Export Dialog */}
      {!!showExportDialog && (
        <RecordExportDialog
          onClose={() => setShowExportDialog(false)}
          onSuccess={() => {
            setShowExportDialog(false);
            loadData();
          }}
        />
      )}
    </div>
  );
}

// ============================================
// Sub-components
// ============================================

function StatCard({ label, value, subText, icon, color }: {
  label: string; value: string; subText: string; icon: string; color: string
}) {
  return (
    <div style={{
      padding: '20px', background: 'var(--arkham-bg-secondary, #ffffff)', borderRadius: '12px',
      border: '1px solid var(--arkham-border, #e5e7eb)', display: 'flex', alignItems: 'center', gap: '16px'
    }}>
      <div style={{
        width: '48px', height: '48px', borderRadius: '10px', background: `${color}15`,
        display: 'flex', alignItems: 'center', justifyContent: 'center', color: color
      }}>
        <Icon name={icon} size={24} />
      </div>
      <div>
        <div style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)', fontWeight: 500 }}>{label}</div>
        <div style={{ fontSize: '24px', fontWeight: 700, margin: '2px 0' }}>{value}</div>
        <div style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)' }}>{subText}</div>
      </div>
    </div>
  );
}

function TabButton({ active, onClick, label, icon, count }: {
  active: boolean; onClick: () => void; label: string; icon: string; count: number
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '16px 24px', border: 'none', background: active ? 'white' : 'transparent',
        borderBottom: active ? '2px solid var(--arkham-bg-accent, #059669)' : '2px solid transparent',
        color: active ? 'var(--arkham-bg-accent, #059669)' : 'var(--arkham-text-muted, #6b7280)',
        fontSize: '15px', fontWeight: active ? 600 : 500, cursor: 'pointer',
        display: 'flex', alignItems: 'center', gap: '8px', transition: 'all 0.2s', marginBottom: '-1px'
      }}
    >
      <Icon name={icon} size={18} /> {label}
      {!!count && (
        <span style={{
          padding: '2px 8px', borderRadius: '12px', background: active ? '#05966915' : '#f3f4f6',
          fontSize: '12px', fontWeight: 600
        }}>{count}</span>
      )}
    </button>
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--arkham-text-muted, #6b7280)' }}>{label}</label>
      {children}
    </div>
  );
}

// ============================================
// Tables & Lists
// ============================================

function ActionLogTable({ actions }: { actions: Record<string, unknown>[] }) {
  if (actions.length === 0) {
    return <EmptyState icon="Search" title="No actions found" desc="Try adjusting your filters or checking a different date range." />;
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '14px' }}>
        <thead>
          <tr style={{ background: 'var(--arkham-bg-tertiary, #f9fafb)', borderBottom: '1px solid var(--arkham-border, #e5e7eb)' }}>
            <th style={{ padding: '12px 24px', fontWeight: 600 }}>Timestamp</th>
            <th style={{ padding: '12px 24px', fontWeight: 600 }}>User</th>
            <th style={{ padding: '12px 24px', fontWeight: 600 }}>Action</th>
            <th style={{ padding: '12px 24px', fontWeight: 600 }}>Target</th>
            <th style={{ padding: '12px 24px', fontWeight: 600 }}>Details</th>
          </tr>
        </thead>
        <tbody>
          {actions.map((action, idx) => (
            <tr key={String(action.id || idx)} style={{
              borderBottom: '1px solid var(--arkham-border, #e5e7eb)',
              background: idx % 2 === 0 ? 'transparent' : 'var(--arkham-bg-tertiary, #fcfcfc)'
            }}>
              <td style={{ padding: '14px 24px', whiteSpace: 'nowrap', fontFamily: 'monospace', color: '#6b7280' }}>
                {String(action.created_at || action.timestamp || '').replace('T', ' ').split('.')[0]}
              </td>
              <td style={{ padding: '14px 24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{ width: '24px', height: '24px', borderRadius: '50%', background: '#e5e7eb', fontSize: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {String(action.user_id || '?').substring(0, 2).toUpperCase()}
                  </div>
                  <span style={{ fontWeight: 500 }}>{String(action.user_id || 'system')}</span>
                </div>
              </td>
              <td style={{ padding: '14px 24px' }}>
                <span style={{
                  padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase',
                  background: getActionColor(String(action.action_type)) + '15', color: getActionColor(String(action.action_type))
                }}>
                  {String(action.action_type || 'unknown')}
                </span>
              </td>
              <td style={{ padding: '14px 24px', color: '#374151' }}>
                <div style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)' }}>{String(action.shard || 'global')}</div>
                <div style={{ fontWeight: 500 }}>{String(action.entity_id || 'N/A')}</div>
              </td>
              <td style={{ padding: '14px 24px', maxWidth: '400px' }}>
                <div style={{
                  fontSize: '13px', color: '#4b5563', overflow: 'hidden', textOverflow: 'ellipsis',
                  display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical'
                }}>
                  {String(action.description || action.details || JSON.stringify(action.metadata || {}))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SessionList({ sessions }: { sessions: Record<string, unknown>[] }) {
  if (sessions.length === 0) return <EmptyState icon="Fingerprint" title="No sessions recorded" desc="User sessions will appear here as they interact with the system." />;
  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {sessions.map((session, idx) => (
        <div key={String(session.id || idx)} style={{
          padding: '16px', background: 'white', border: '1px solid var(--arkham-border, #e5e7eb)',
          borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{ width: '40px', height: '40px', borderRadius: '8px', background: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4b5563' }}>
              <Icon name="Monitor" size={20} />
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: '15px' }}>Session: {String(session.session_id || session.id).substring(0, 12)}...</div>
              <div style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)' }}>User: {String(session.user_id || 'unknown')}</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '48px', alignItems: 'center' }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)', fontWeight: 600, textTransform: 'uppercase' }}>Timeline</div>
              <div style={{ fontSize: '13px', fontWeight: 500 }}>
                {String(session.start_time || '').split('T')[0]} <span style={{ color: '#9ca3af', margin: '0 4px' }}>→</span> {String(session.end_time || 'Active').split('T')[0]}
              </div>
            </div>
            <div style={{ textAlign: 'right', minWidth: '80px' }}>
              <div style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)', fontWeight: 600, textTransform: 'uppercase' }}>Actions</div>
              <div style={{ fontSize: '16px', fontWeight: 700, color: '#059669' }}>{String(session.action_count || '0')}</div>
            </div>
            <button style={{ padding: '6px', borderRadius: '6px', border: '1px solid #e5e7eb', background: 'transparent', cursor: 'pointer', color: '#6b7280' }}><Icon name="ChevronRight" size={18} /></button>
          </div>
        </div>
      ))}
    </div>
  );
}

function ExportList({ exports }: { exports: Record<string, unknown>[] }) {
  if (exports.length === 0) return <EmptyState icon="FileJson" title="No exports found" desc="History of generated reports and data extracts will appear here." />;
  return (
    <div style={{ padding: '24px', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px' }}>
      {exports.map((exp, idx) => (
        <div key={String(exp.id || idx)} style={{
          padding: '20px', background: 'white', border: '1px solid var(--arkham-border, #e5e7eb)',
          borderRadius: '12px', position: 'relative', overflow: 'hidden'
        }}>
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '4px', background: getFormatColor(String(exp.export_format)) }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
            <div style={{ width: '32px', height: '32px', borderRadius: '6px', background: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Icon name="FileBox" size={18} /></div>
            <span style={{ fontSize: '11px', fontWeight: 800, padding: '2px 6px', borderRadius: '4px', background: '#f3f4f6', color: '#4b5563', textTransform: 'uppercase' }}>{String(exp.export_format)}</span>
          </div>
          <div style={{ fontWeight: 600, fontSize: '15px', marginBottom: '4px' }}>Export #{String(exp.export_id || exp.id).substring(0, 8)}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: '#6b7280' }}><Icon name="Clock" size={14} /> {String(exp.created_at || '').split('T')[0]}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: '#6b7280' }}><Icon name="User" size={14} /> {String(exp.user_id || 'system')}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: '#6b7280' }}><Icon name="Layers" size={14} /> {String(exp.row_count || '0')} records</div>
          </div>
          <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px dashed #e5e7eb', display: 'flex', justifyContent: 'flex-end' }}>
            <button style={{ fontSize: '12px', fontWeight: 600, color: '#059669', background: 'transparent', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}><Icon name="Eye" size={14} /> View Filters</button>
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================
// Dialogs
// ============================================

function RecordExportDialog({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const { toast } = useToast();
  const [format, setFormat] = useState('JSON');
  const [rowCount, setRowCount] = useState('0');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    try {
      setSubmitting(true);
      await api.recordExport({
        export_format: format,
        row_count: parseInt(rowCount) || 0,
        filters_applied: { manual_entry: true },
      });
      toast.success('Export record added to audit trail');
      onSuccess();
    } catch (err) {
      toast.error(`Failed to record export: ${String(err)}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)'
    }} onClick={onClose}>
      <div
        style={{
          background: 'white', width: '400px', borderRadius: '16px', padding: '24px',
          boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)', border: '1px solid #e5e7eb'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ margin: '0 0 8px 0', fontSize: '20px', fontWeight: 700 }}>Record Manual Export</h2>
        <p style={{ margin: '0 0 24px 0', fontSize: '14px', color: '#6b7280' }}>
          Document an external data export for forensic integrity.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 600 }}>Export Format</label>
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value)}
              style={{ padding: '10px', borderRadius: '8px', border: '1px solid #e5e7eb' }}
            >
              <option value="JSON">JSON (Machine Readable)</option>
              <option value="CSV">CSV (Spreadsheet)</option>
              <option value="PDF">PDF (Document)</option>
              <option value="DOCX">DOCX (Word)</option>
            </select>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 600 }}>Record Count</label>
            <input
              type="number"
              value={rowCount}
              onChange={(e) => setRowCount(e.target.value)}
              style={{ padding: '10px', borderRadius: '8px', border: '1px solid #e5e7eb' }}
            />
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
          <button
            onClick={onClose}
            style={{ padding: '10px 16px', borderRadius: '8px', border: '1px solid #e5e7eb', background: 'transparent', cursor: 'pointer' }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            style={{
              padding: '10px 16px', borderRadius: '8px', border: 'none',
              background: '#059669', color: 'white', fontWeight: 600, cursor: 'pointer',
              opacity: submitting ? 0.7 : 1
            }}
          >
            {submitting ? 'Recording...' : 'Record Export'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Utilities
// ============================================

function EmptyState({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div style={{ padding: '80px 40px', textAlign: 'center', color: '#9ca3af' }}>
      <div style={{
        width: '64px', height: '64px', borderRadius: '50%', background: '#f3f4f6',
        display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px'
      }}>
        <Icon name={icon} size={32} />
      </div>
      <h3 style={{ margin: '0 0 8px 0', color: '#4b5563', fontSize: '18px' }}>{title}</h3>
      <p style={{ margin: 0, fontSize: '14px', maxWidth: '300px', marginInline: 'auto' }}>{desc}</p>
    </div>
  );
}

function getActionColor(type: string): string {
  const t = type.toLowerCase();
  if (t.includes('create')) return '#059669';
  if (t.includes('update')) return '#2563eb';
  if (t.includes('delete')) return '#dc2626';
  if (t.includes('export')) return '#7c3aed';
  if (t.includes('read')) return '#0891b2';
  return '#6b7280';
}

function getFormatColor(format: string): string {
  const f = format.toUpperCase();
  if (f === 'PDF') return '#dc2626';
  if (f === 'JSON') return '#ea580c';
  if (f === 'CSV') return '#059669';
  if (f === 'DOCX') return '#2563eb';
  return '#9ca3af';
}
