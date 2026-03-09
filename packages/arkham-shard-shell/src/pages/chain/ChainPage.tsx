import { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';
import type { ChainListItem, ChainItem, ItemStatus } from './types';

interface ExtendedChainListItem extends ChainListItem {
  metadata?: Record<string, unknown>;
}

export function ChainPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const itemId = searchParams.get('itemId');

  const setView = (id: string | null) => {
    const newParams = new URLSearchParams(searchParams);
    if (id) {
      newParams.set('itemId', id);
    } else {
      newParams.delete('itemId');
    }
    setSearchParams(newParams);
  };

  if (!!itemId && itemId !== '') {
    return <ItemDetailView itemId={itemId} onBack={() => setView(null)} />;
  }

  return <ItemListView onSelect={(id) => setView(id)} />;
}

function ItemListView({ onSelect }: { onSelect: (id: string) => void }) {
  const { toast } = useToast();
  const [items, setItems] = useState<ExtendedChainListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const loadItems = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listItems();
      const itemsList = Array.isArray(data.items) ? data.items : [];

      const mapped: ExtendedChainListItem[] = itemsList.map((it: Record<string, unknown>) => ({
        id: String(it.id || ''),
        title: String(it.title || ''),
        description: String(it.description || ''),
        status: (it.status as ItemStatus) || 'active',
        created_at: String(it.created_at || ''),
        updated_at: String(it.updated_at || ''),
        metadata: (it.metadata as Record<string, unknown>) || {}
      }));

      setItems(mapped);
    } catch (err) {
      toast.error(`Failed to load items: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const filteredItems = useMemo(() => {
    return items.filter(it =>
      String(it.title).toLowerCase().includes(search.toLowerCase()) ||
      String(it.description).toLowerCase().includes(search.toLowerCase())
    );
  }, [items, search]);

  if (loading) return <LoadingSkeleton />;

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '10px', margin: 0 }}>
            <Icon name="ShieldCheck" size={28} color="#3b82f6" /> Evidence Chain of Custody
          </h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', marginTop: '6px', fontSize: '14px' }}>
            Cryptographically verifiable evidence tracking and provenance management
          </p>
        </div>
        <button
          onClick={() => setShowCreateDialog(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '10px 20px', background: '#3b82f6', color: 'white',
            border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 600,
            transition: 'background 0.2s'
          }}
        >
          <Icon name="Plus" size={18} /> New Evidence Item
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '32px' }}>
        <StatCard label="Total Evidence" value={String(items.length)} icon="Database" color="#3b82f6" />
        <StatCard
          label="Verified Secure"
          value={String(items.filter((it) => it.metadata?.integrity === 'verified').length)}
          icon="CheckCircle" color="#10b981"
        />
        <StatCard
          label="Tamper Alerts"
          value={String(items.filter((it) => it.metadata?.integrity === 'tampered').length)}
          icon="AlertTriangle" color="#ef4444"
        />
        <StatCard
          label="Pending Review"
          value={String(items.filter((it) => !it.metadata?.integrity || it.metadata?.integrity === 'unverified').length)}
          icon="Clock" color="#6b7280"
        />
      </div>

      <div style={{ position: 'relative', marginBottom: '24px' }}>
        <Icon name="Search" size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }} />
        <input
          type="text"
          placeholder="Search by title, description, or document ID..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: '100%', padding: '12px 12px 12px 42px', borderRadius: '10px',
            border: '1px solid var(--arkham-border, #e5e7eb)', fontSize: '15px',
            background: 'var(--arkham-bg-secondary, #ffffff)', color: 'inherit',
            boxSizing: 'border-box'
          }}
        />
      </div>

      {filteredItems.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '64px', background: 'var(--arkham-bg-secondary, #f9fafb)', borderRadius: '12px', border: '1px dashed var(--arkham-border, #e5e7eb)' }}>
          <Icon name="Inbox" size={48} color="#9ca3af" />
          <h3 style={{ marginTop: '16px', fontSize: '18px', fontWeight: 500 }}>No evidence items found</h3>
          <p style={{ color: '#6b7280', fontSize: '14px' }}>{search ? 'Try adjusting your search terms' : 'Get started by creating your first evidence item'}</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '12px' }}>
          {filteredItems.map((item) => (
            <EvidenceRow key={item.id} item={item} onClick={() => onSelect(item.id)} />
          ))}
        </div>
      )}

      {!!showCreateDialog && (
        <CreateItemDialog
          onClose={() => setShowCreateDialog(false)}
          onCreated={() => { setShowCreateDialog(false); loadItems(); }}
        />
      )}
    </div>
  );
}

function ItemDetailView({ itemId, onBack }: { itemId: string; onBack: () => void }) {
  const { toast } = useToast();
  const [item, setItem] = useState<ChainItem | null>(null);
  const [history, setHistory] = useState<Record<string, unknown>[]>([]);
  const [reports, setReports] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [integrityResult, setIntegrityResult] = useState<{valid: boolean; current_hash: string; stored_hash: string} | null>(null);
  const [showLogDialog, setShowLogDialog] = useState(false);

  const loadDetail = useCallback(async () => {
    try {
      setLoading(true);
      const [itemData, historyData, reportsData] = await Promise.all([
        api.getItem(itemId),
        api.getDocumentHistory(itemId),
        api.listReports(itemId)
      ]);

      setItem(itemData as unknown as ChainItem);
      setHistory(Array.isArray(historyData.history) ? historyData.history as Record<string, unknown>[] : []);
      setReports(Array.isArray(reportsData.reports) ? reportsData.reports as Record<string, unknown>[] : []);
    } catch (err) {
      toast.error(`Failed to load evidence details: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [itemId, toast]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const handleVerify = async () => {
    try {
      setVerifying(true);
      const result = await api.verifyDocumentIntegrity(itemId);
      setIntegrityResult(result);
      if (result.valid) {
        toast.success('Integrity verified successfully');
      } else {
        toast.error('Integrity check failed: Tamper detected!');
      }
    } catch (err) {
      toast.error(`Verification error: ${err}`);
    } finally {
      setVerifying(false);
    }
  };

  const handleGenerateReport = async () => {
    try {
      toast.info('Generating provenance report...');
      await api.generateProvenanceReport(itemId);
      toast.success('Report generated successfully');
      const reportsData = await api.listReports(itemId);
      setReports(Array.isArray(reportsData.reports) ? reportsData.reports as Record<string, unknown>[] : []);
    } catch (err) {
      toast.error(`Failed to generate report: ${err}`);
    }
  };

  const handleCopyHash = (hash: string) => {
    navigator.clipboard.writeText(hash);
    toast.info('Hash copied to clipboard');
  };

  if (loading) return <LoadingSkeleton />;
  if (!item) return <div style={{ padding: '40px', textAlign: 'center' }}>Item not found. <button onClick={onBack}>Go back</button></div>;

  const currentHash = String(integrityResult?.current_hash || (item.metadata as Record<string, unknown>)?.hash || 'Not hashed');

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <button
          onClick={onBack}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--arkham-text-muted, #6b7280)', fontSize: '14px',
            padding: '4px 8px', borderRadius: '4px'
          }}
        >
          <Icon name="ArrowLeft" size={16} /> Back to Evidence List
        </button>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={handleVerify}
            disabled={verifying}
            style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '8px 16px', background: 'var(--arkham-bg-secondary, #ffffff)',
              border: '1px solid var(--arkham-border, #e5e7eb)', borderRadius: '6px',
              cursor: 'pointer', fontWeight: 500, opacity: verifying ? 0.6 : 1
            }}
          >
            <Icon name="Shield" size={16} color={verifying ? '#9ca3af' : '#3b82f6'} /> {verifying ? 'Verifying...' : 'Verify Integrity'}
          </button>
          <button
            onClick={() => setShowLogDialog(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '8px 16px', background: 'var(--arkham-bg-secondary, #ffffff)',
              border: '1px solid var(--arkham-border, #e5e7eb)', borderRadius: '6px',
              cursor: 'pointer', fontWeight: 500
            }}
          >
            <Icon name="ClipboardList" size={16} color="#10b981" /> Log Event
          </button>
          <button
            onClick={handleGenerateReport}
            style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '8px 16px', background: '#3b82f6', color: 'white',
              border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 500
            }}
          >
            <Icon name="FileText" size={16} /> Generate Report
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
        <div>
          <div style={{
            padding: '24px', background: 'var(--arkham-bg-secondary, #ffffff)',
            borderRadius: '12px', border: '1px solid var(--arkham-border, #e5e7eb)',
            marginBottom: '24px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <h1 style={{ fontSize: '24px', fontWeight: 600, margin: '0 0 8px 0' }}>{String(item.title)}</h1>
                <p style={{ color: '#6b7280', margin: 0, lineHeight: 1.5 }}>{String(item.description || 'No description provided')}</p>
              </div>
              <IntegrityBadge status={integrityResult ? (integrityResult.valid ? 'verified' : 'tampered') : ((item.metadata as Record<string, unknown>)?.integrity as any || 'unverified')} large />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginTop: '24px', borderTop: '1px solid #f3f4f6', paddingTop: '24px' }}>
              <div>
                <span style={{ fontSize: '12px', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>Evidence ID</span>
                <div style={{ fontSize: '14px', fontWeight: 500, marginTop: '4px', fontFamily: 'monospace' }}>{String(item.id)}</div>
              </div>
              <div>
                <span style={{ fontSize: '12px', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>Project</span>
                <div style={{ fontSize: '14px', fontWeight: 500, marginTop: '4px' }}>{String(item.project_id || 'Global')}</div>
              </div>
            </div>

            <div style={{ marginTop: '20px', padding: '12px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '11px', fontWeight: 700, color: '#64748b' }}>SHA-256 HASH</span>
                <button
                  onClick={() => handleCopyHash(currentHash)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#3b82f6', fontSize: '11px', fontWeight: 600 }}
                >
                  COPY
                </button>
              </div>
              <div style={{ fontSize: '12px', fontFamily: 'monospace', wordBreak: 'break-all', color: '#1e293b' }}>
                {currentHash === 'Not hashed' ? '0x' + '0'.repeat(64) : currentHash}
              </div>
              {!!integrityResult && (
                <div style={{ marginTop: '8px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px', color: integrityResult.valid ? '#10b981' : '#ef4444' }}>
                  <Icon name={integrityResult.valid ? "Check" : "X"} size={14} />
                  {integrityResult.valid ? 'Current hash matches stored hash' : 'Hash mismatch! Verification failed'}
                </div>
              )}
            </div>
          </div>

          <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Icon name="History" size={18} /> Custody Timeline
          </h2>
          <div style={{ paddingLeft: '20px', borderLeft: '2px solid #e5e7eb', marginLeft: '10px' }}>
            {history.length === 0 ? (
              <p style={{ color: '#9ca3af', fontSize: '14px', padding: '10px 0' }}>No custody events recorded yet.</p>
            ) : (
              history.map((event, idx) => (
                <TimelineEvent key={idx} event={event} isLast={idx === history.length - 1} />
              ))
            )}
          </div>
        </div>

        <div>
          <div style={{
            padding: '20px', background: 'var(--arkham-bg-secondary, #ffffff)',
            borderRadius: '12px', border: '1px solid var(--arkham-border, #e5e7eb)',
            marginBottom: '24px'
          }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, margin: '0 0 16px 0' }}>Item Status</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <StatusItem label="Current Status" value={String(item.status)} icon="Activity" />
              <StatusItem label="Created" value={formatDate(item.created_at)} icon="Calendar" />
              <StatusItem label="Last Updated" value={formatDate(item.updated_at)} icon="RefreshCw" />
              <StatusItem label="Created By" value={String(item.created_by || 'Unknown')} icon="User" />
            </div>
          </div>

          <div style={{
            padding: '20px', background: 'var(--arkham-bg-secondary, #ffffff)',
            borderRadius: '12px', border: '1px solid var(--arkham-border, #e5e7eb)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>Provenance Reports</h3>
              <span style={{ fontSize: '12px', background: '#f3f4f6', padding: '2px 8px', borderRadius: '10px', fontWeight: 600 }}>{reports.length}</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {reports.length === 0 ? (
                <p style={{ color: '#9ca3af', fontSize: '13px', textAlign: 'center', padding: '20px 0' }}>No reports generated.</p>
              ) : (
                reports.map((report, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '10px', borderRadius: '8px', border: '1px solid #f3f4f6',
                      display: 'flex', alignItems: 'center', gap: '10px',
                      cursor: 'pointer', transition: 'background 0.2s'
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = '#f9fafb')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    <div style={{ background: '#eff6ff', padding: '8px', borderRadius: '6px' }}>
                      <Icon name="FileText" size={16} color="#3b82f6" />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: '13px', fontWeight: 600 }}>Report — {String(report.report_id || 'ID Unknown').substring(0, 8)}</div>
                      <div style={{ fontSize: '11px', color: '#9ca3af' }}>Generated {formatDate(String(report.created_at || ''))}</div>
                    </div>
                    <Icon name="Download" size={14} color="#6b7280" />
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {!!showLogDialog && (
        <LogEventDialog
          documentId={itemId}
          onClose={() => setShowLogDialog(false)}
          onCreated={() => { setShowLogDialog(false); loadDetail(); }}
        />
      )}
    </div>
  );
}

function EvidenceRow({ item, onClick }: { item: ExtendedChainListItem; onClick: () => void }) {
  const integrity = String(item.metadata?.integrity || 'unverified') as 'verified' | 'unverified' | 'tampered';

  return (
    <div
      onClick={onClick}
      style={{
        padding: '16px 20px', background: 'var(--arkham-bg-secondary, #ffffff)',
        borderRadius: '10px', border: '1px solid var(--arkham-border, #e5e7eb)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        cursor: 'pointer', transition: 'all 0.2s', boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = '#3b82f6';
        e.currentTarget.style.transform = 'translateY(-1px)';
        e.currentTarget.style.boxShadow = '0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--arkham-border, #e5e7eb)';
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.boxShadow = '0 1px 2px rgba(0,0,0,0.05)';
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {String(item.title)}
          </h3>
          <IntegrityBadge status={integrity} />
        </div>
        <p style={{ margin: 0, color: '#6b7280', fontSize: '14px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {String(item.description || 'No description')}
        </p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '20px', marginLeft: '24px' }}>
        <div style={{ textAlign: 'right', fontSize: '12px', color: '#9ca3af' }}>
          <div style={{ fontWeight: 600, color: '#6b7280' }}>ID: {String(item.id).substring(0, 8)}</div>
          <div>Updated {formatDate(item.updated_at)}</div>
        </div>
        <Icon name="ChevronRight" size={20} color="#d1d5db" />
      </div>
    </div>
  );
}

function IntegrityBadge({ status, large }: { status: 'verified' | 'unverified' | 'tampered'; large?: boolean }) {
  const configs = {
    verified: { icon: 'ShieldCheck', color: '#10b981', bg: '#ecfdf5', label: 'VERIFIED' },
    tampered: { icon: 'AlertTriangle', color: '#ef4444', bg: '#fef2f2', label: 'TAMPERED' },
    unverified: { icon: 'Shield', color: '#6b7280', bg: '#f3f4f6', label: 'UNVERIFIED' }
  };

  const config = configs[status] || configs.unverified;

  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      padding: large ? '4px 12px' : '2px 8px', borderRadius: '12px',
      background: config.bg, color: config.color,
      fontSize: large ? '12px' : '10px', fontWeight: 700, border: `1px solid ${config.color}20`
    }}>
      <Icon name={config.icon} size={large ? 14 : 10} />
      {config.label}
    </div>
  );
}

function StatCard({ label, value, icon, color }: { label: string; value: string; icon: string; color: string }) {
  return (
    <div style={{
      padding: '16px', background: 'var(--arkham-bg-secondary, #ffffff)',
      borderRadius: '10px', border: '1px solid var(--arkham-border, #e5e7eb)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#6b7280', fontSize: '12px', fontWeight: 600, marginBottom: '8px' }}>
        <Icon name={icon} size={14} color={color} /> {label.toUpperCase()}
      </div>
      <div style={{ fontSize: '24px', fontWeight: 700, color: '#111827' }}>{value}</div>
    </div>
  );
}

function StatusItem({ label, value, icon }: { label: string; value: string; icon: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
      <div style={{ background: '#f3f4f6', padding: '6px', borderRadius: '6px' }}>
        <Icon name={icon} size={14} color="#6b7280" />
      </div>
      <div>
        <div style={{ fontSize: '11px', color: '#9ca3af', fontWeight: 600 }}>{label}</div>
        <div style={{ fontSize: '13px', fontWeight: 500 }}>{value}</div>
      </div>
    </div>
  );
}

function TimelineEvent({ event, isLast }: { event: Record<string, unknown>; isLast: boolean }) {
  return (
    <div style={{ position: 'relative', paddingBottom: isLast ? 0 : '24px' }}>
      <div style={{
        position: 'absolute', left: '-27px', top: '0',
        width: '12px', height: '12px', borderRadius: '50%',
        background: '#3b82f6', border: '3px solid white', boxShadow: '0 0 0 1px #e5e7eb'
      }} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
        <div style={{ fontSize: '14px', fontWeight: 700 }}>{String(event.action || 'Unknown Action')}</div>
        <div style={{ fontSize: '12px', color: '#9ca3af' }}>{formatDate(String(event.timestamp || event.created_at || ''))}</div>
      </div>

      <div style={{ fontSize: '13px', color: '#4b5563', marginBottom: '4px' }}>
        <span style={{ fontWeight: 600 }}>Actor:</span> {String(event.actor || 'System')}
      </div>
      {!!event.location && (
        <div style={{ fontSize: '13px', color: '#4b5563', marginBottom: '4px' }}>
          <span style={{ fontWeight: 600 }}>Location:</span> {String(event.location)}
        </div>
      )}
      {!!event.notes && (
        <div style={{
          fontSize: '13px', color: '#6b7280', fontStyle: 'italic',
          background: '#f9fafb', padding: '8px', borderRadius: '6px', marginTop: '8px'
        }}>
          "{String(event.notes)}"
        </div>
      )}
    </div>
  );
}

function CreateItemDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    if (!title.trim()) { toast.error('Title is required'); return; }
    try {
      setSaving(true);
      await api.createItem({
        title: title.trim(),
        description: description.trim(),
        metadata: { integrity: 'unverified' }
      });
      toast.success('Evidence item created');
      onCreated();
    } catch (err) {
      toast.error(`Failed to create item: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
    }} onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--arkham-bg-primary, #ffffff)', padding: '24px', borderRadius: '12px',
          width: '450px', maxWidth: '95vw', border: '1px solid var(--arkham-border, #e5e7eb)'
        }}
      >
        <h2 style={{ fontSize: '20px', fontWeight: 600, margin: '0 0 20px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Icon name="Plus" size={20} /> New Evidence Item
        </h2>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '6px' }}>Title</label>
          <input
            type="text" value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. CCTV Footage - South Entrance"
            style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '14px', boxSizing: 'border-box' }}
          />
        </div>

        <div style={{ marginBottom: '24px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '6px' }}>Description</label>
          <textarea
            rows={3} value={description} onChange={(e) => setDescription(e.target.value)}
            placeholder="Detailed description of the evidence..."
            style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '14px', boxSizing: 'border-box', resize: 'vertical' }}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button onClick={onClose} style={{ padding: '8px 16px', background: 'none', border: '1px solid #d1d5db', borderRadius: '6px', cursor: 'pointer' }}>Cancel</button>
          <button
            onClick={handleCreate} disabled={saving}
            style={{
              padding: '8px 16px', background: '#3b82f6', color: 'white',
              border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600,
              opacity: saving ? 0.6 : 1
            }}
          >
            {saving ? 'Creating...' : 'Create Item'}
          </button>
        </div>
      </div>
    </div>
  );
}

function LogEventDialog({ documentId, onClose, onCreated }: { documentId: string; onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [action, setAction] = useState('Transfer');
  const [actor, setActor] = useState('');
  const [location, setLocation] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const handleLog = async () => {
    if (!actor.trim()) { toast.error('Actor name is required'); return; }
    try {
      setSaving(true);
      await api.logCustodyEvent({
        document_id: documentId,
        action,
        actor: actor.trim(),
        location: location.trim(),
        notes: notes.trim()
      });
      toast.success('Custody event logged');
      onCreated();
    } catch (err) {
      toast.error(`Failed to log event: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  const ACTIONS = ['Collection', 'Transfer', 'Storage', 'Analysis', 'Observation', 'Disposal'];

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
    }} onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--arkham-bg-primary, #ffffff)', padding: '24px', borderRadius: '12px',
          width: '450px', maxWidth: '95vw', border: '1px solid var(--arkham-border, #e5e7eb)'
        }}
      >
        <h2 style={{ fontSize: '20px', fontWeight: 600, margin: '0 0 20px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Icon name="ClipboardList" size={20} /> Log Custody Event
        </h2>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '6px' }}>Action</label>
            <select
              value={action} onChange={(e) => setAction(e.target.value)}
              style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '14px' }}
            >
              {ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '6px' }}>Actor</label>
            <input
              type="text" value={actor} onChange={(e) => setActor(e.target.value)}
              placeholder="e.g. Det. Smith"
              style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '14px', boxSizing: 'border-box' }}
            />
          </div>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '6px' }}>Location</label>
          <input
            type="text" value={location} onChange={(e) => setLocation(e.target.value)}
            placeholder="e.g. Evidence Locker 402"
            style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '14px', boxSizing: 'border-box' }}
          />
        </div>

        <div style={{ marginBottom: '24px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '6px' }}>Notes</label>
          <textarea
            rows={2} value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="Optional notes or context..."
            style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '14px', boxSizing: 'border-box', resize: 'vertical' }}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button onClick={onClose} style={{ padding: '8px 16px', background: 'none', border: '1px solid #d1d5db', borderRadius: '6px', cursor: 'pointer' }}>Cancel</button>
          <button
            onClick={handleLog} disabled={saving}
            style={{
              padding: '8px 16px', background: '#10b981', color: 'white',
              border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600,
              opacity: saving ? 0.6 : 1
            }}
          >
            {saving ? 'Logging...' : 'Log Event'}
          </button>
        </div>
      </div>
    </div>
  );
}

function formatDate(dateStr: string) {
  if (!dateStr) return 'N/A';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch {
    return dateStr;
  }
}
