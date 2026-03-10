/**
 * ComparatorPage - Discrimination Comparator Analysis
 *
 * Maps claimant vs comparator treatment across incidents for s.13/s.26 Equality Act claims.
 * Tracks incidents, comparators, and divergences in treatment with significance scoring.
 */

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';

type TabKey = 'incidents' | 'comparators' | 'divergences';

export function ComparatorPage() {
  const [searchParams] = useSearchParams();
  const itemId = searchParams.get('itemId');

  if (!!itemId && itemId !== '') {
    return <ItemDetailView itemId={itemId} />;
  }

  return <ComparatorListView />;
}

function ComparatorListView() {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<TabKey>('incidents');
  const [loading, setLoading] = useState(true);

  const [incidents, setIncidents] = useState<Record<string, unknown>[]>([]);
  const [comparators, setComparators] = useState<Record<string, unknown>[]>([]);
  const [divergences, setDivergences] = useState<Record<string, unknown>[]>([]);

  const [showCreateIncident, setShowCreateIncident] = useState(false);
  const [showCreateComparator, setShowCreateComparator] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [incData, compData, divData] = await Promise.all([
        api.listIncidents().catch(() => ({ incidents: [] })),
        api.listComparators().catch(() => ({ comparators: [] })),
        api.listDivergences().catch(() => ({ divergences: [] })),
      ]);

      setIncidents(incData.incidents || []);
      setComparators(compData.comparators || []);
      setDivergences(divData.divergences || []);
    } catch (err) {
      toast.error(`Failed to load comparator data: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const tabs: { key: TabKey; label: string; icon: string; count: number }[] = [
    { key: 'incidents', label: 'Incidents', icon: 'AlertCircle', count: incidents.length },
    { key: 'comparators', label: 'Comparators', icon: 'Users', count: comparators.length },
    { key: 'divergences', label: 'Divergences', icon: 'GitCompare', count: divergences.length },
  ];

  if (loading) return <LoadingSkeleton />;

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <Icon name="Scale" size={24} /> Discrimination Comparator
          </h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', marginTop: '4px', fontSize: '14px' }}>
            Compare treatment of claimant vs comparators across workplace incidents
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={() => setShowCreateIncident(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '8px 16px', background: 'var(--arkham-bg-secondary, #f3f4f6)',
              color: 'var(--arkham-text-primary, #111827)',
              border: '1px solid var(--arkham-border, #e5e7eb)', borderRadius: '6px', cursor: 'pointer', fontWeight: 500,
            }}
          >
            <Icon name="Plus" size={16} /> Incident
          </button>
          <button
            onClick={() => setShowCreateComparator(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '8px 16px', background: '#3b82f6', color: 'white',
              border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 500,
            }}
          >
            <Icon name="UserPlus" size={16} /> Comparator
          </button>
        </div>
      </div>

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

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {activeTab === 'incidents' && (
          incidents.length === 0 ? <EmptyState type="incidents" /> : incidents.map(inc => <IncidentRow key={String(inc.incident_id || inc.id)} incident={inc} />)
        )}
        {activeTab === 'comparators' && (
          comparators.length === 0 ? <EmptyState type="comparators" /> : comparators.map(comp => <ComparatorRow key={String(comp.comparator_id || comp.id)} comparator={comp} />)
        )}
        {activeTab === 'divergences' && (
          divergences.length === 0 ? <EmptyState type="divergences" /> : divergences.map(div => <DivergenceCard key={String(div.divergence_id || div.id)} divergence={div} />)
        )}
      </div>

      {!!showCreateIncident && (
        <CreateIncidentDialog
          onClose={() => setShowCreateIncident(false)}
          onCreated={() => { setShowCreateIncident(false); loadData(); }}
        />
      )}
      {!!showCreateComparator && (
        <CreateComparatorDialog
          onClose={() => setShowCreateComparator(false)}
          onCreated={() => { setShowCreateComparator(false); loadData(); }}
        />
      )}
    </div>
  );
}

function IncidentRow({ incident }: { incident: Record<string, unknown> }) {
  const [, setSearchParams] = useSearchParams();
  const id = String(incident.incident_id || incident.id || '');

  return (
    <div
      onClick={() => setSearchParams({ itemId: id })}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '16px', borderRadius: '8px', border: '1px solid var(--arkham-border, #e5e7eb)',
        background: 'var(--arkham-bg-secondary, white)', cursor: 'pointer', transition: 'border-color 0.2s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{
          width: '40px', height: '40px', borderRadius: '8px', background: '#fef2f2',
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#ef4444'
        }}>
          <Icon name="AlertCircle" size={20} />
        </div>
        <div>
          <div style={{ fontWeight: 600, fontSize: '15px' }}>{String(incident.description || 'Untitled Incident')}</div>
          <div style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)', marginTop: '2px' }}>
            {!!incident.date && <span>{String(incident.date)}</span>}
          </div>
        </div>
      </div>
      <Icon name="ChevronRight" size={16} color="#9ca3af" />
    </div>
  );
}

function ComparatorRow({ comparator }: { comparator: Record<string, unknown> }) {
  const [, setSearchParams] = useSearchParams();
  const id = String(comparator.comparator_id || comparator.id || '');

  return (
    <div
      onClick={() => setSearchParams({ itemId: id })}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '16px', borderRadius: '8px', border: '1px solid var(--arkham-border, #e5e7eb)',
        background: 'var(--arkham-bg-secondary, white)', cursor: 'pointer',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{
          width: '40px', height: '40px', borderRadius: '8px', background: '#eff6ff',
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#3b82f6'
        }}>
          <Icon name="User" size={20} />
        </div>
        <div>
          <div style={{ fontWeight: 600, fontSize: '15px' }}>{String(comparator.name || 'Anonymous Comparator')}</div>
          <div style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)', marginTop: '2px' }}>
            {String(comparator.characteristic || 'No characteristic assigned')}
          </div>
        </div>
      </div>
      <Icon name="ChevronRight" size={16} color="#9ca3af" />
    </div>
  );
}

function DivergenceCard({ divergence }: { divergence: Record<string, unknown> }) {
  const score = Number(divergence.significance_score || 0);

  let color = '#10b981';
  if (score >= 0.7) color = '#ef4444';
  else if (score >= 0.4) color = '#f59e0b';

  return (
    <div style={{
      padding: '16px', borderRadius: '8px', border: '1px solid var(--arkham-border, #e5e7eb)',
      background: 'var(--arkham-bg-secondary, white)', borderLeft: `4px solid ${color}`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
        <div style={{ fontWeight: 600, color: 'var(--arkham-text-primary, #111827)' }}>
          {String(divergence.description || 'Treatment Divergence')}
        </div>
        <div style={{
          fontSize: '11px', fontWeight: 700, padding: '2px 8px', borderRadius: '12px',
          background: `${color}15`, color, textTransform: 'uppercase'
        }}>
          Score: {score.toFixed(2)}
        </div>
      </div>
      <div style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        {!!divergence.incident_id && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Icon name="Link" size={12} /> Incident ID: {String(divergence.incident_id)}
          </div>
        )}
      </div>
    </div>
  );
}

function CreateIncidentDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [description, setDescription] = useState('');
  const [date, setDate] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!description.trim()) { toast.error('Description is required'); return; }
    try {
      setSaving(true);
      await api.createIncident({
        description: description.trim(),
        date: date || undefined,
      });
      toast.success('Incident created');
      onCreated();
    } catch (err) {
      toast.error(`Failed to create incident: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: 'var(--arkham-bg-primary, white)', borderRadius: '12px',
        padding: '24px', width: '480px', maxWidth: '90vw', border: '1px solid var(--arkham-border, #e5e7eb)',
      }}>
        <h2 style={{ margin: '0 0 20px 0', fontSize: '18px', fontWeight: 600 }}>Create New Incident</h2>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px' }}>Description</label>
          <textarea
            value={description} onChange={e => setDescription(e.target.value)}
            placeholder="Describe what happened..." rows={3}
            style={{
              width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid var(--arkham-border, #d1d5db)',
              fontSize: '14px', background: 'transparent', color: 'inherit', resize: 'vertical', boxSizing: 'border-box',
            }}
          />
        </div>

        <div style={{ marginBottom: '24px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px' }}>Date (Optional)</label>
          <input
            type="date" value={date} onChange={e => setDate(e.target.value)}
            style={{
              width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid var(--arkham-border, #d1d5db)',
              fontSize: '14px', background: 'transparent', color: 'inherit', boxSizing: 'border-box',
            }}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button onClick={onClose} style={{
            padding: '8px 16px', borderRadius: '6px', border: '1px solid var(--arkham-border, #d1d5db)',
            background: 'transparent', cursor: 'pointer', fontSize: '14px', color: 'inherit',
          }}>Cancel</button>
          <button onClick={handleSubmit} disabled={saving} style={{
            padding: '8px 16px', borderRadius: '6px', border: 'none', background: '#3b82f6',
            color: 'white', cursor: 'pointer', fontWeight: 600, fontSize: '14px', opacity: saving ? 0.7 : 1,
          }}>
            {saving ? 'Creating...' : 'Create Incident'}
          </button>
        </div>
      </div>
    </div>
  );
}

function CreateComparatorDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [name, setName] = useState('');
  const [characteristic, setCharacteristic] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!name.trim()) { toast.error('Name is required'); return; }
    try {
      setSaving(true);
      await api.createComparator({
        name: name.trim(),
        characteristic: characteristic.trim() || undefined,
      });
      toast.success('Comparator created');
      onCreated();
    } catch (err) {
      toast.error(`Failed to create comparator: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: 'var(--arkham-bg-primary, white)', borderRadius: '12px',
        padding: '24px', width: '480px', maxWidth: '90vw', border: '1px solid var(--arkham-border, #e5e7eb)',
      }}>
        <h2 style={{ margin: '0 0 20px 0', fontSize: '18px', fontWeight: 600 }}>Add Comparator</h2>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px' }}>Name / Identifier</label>
          <input
            value={name} onChange={e => setName(e.target.value)}
            placeholder="e.g. John Smith or 'Employee B'"
            style={{
              width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid var(--arkham-border, #d1d5db)',
              fontSize: '14px', background: 'transparent', color: 'inherit', boxSizing: 'border-box',
            }}
          />
        </div>

        <div style={{ marginBottom: '24px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px' }}>Characteristic (Optional)</label>
          <input
            value={characteristic} onChange={e => setCharacteristic(e.target.value)}
            placeholder="e.g. No disability, Different age group..."
            style={{
              width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid var(--arkham-border, #d1d5db)',
              fontSize: '14px', background: 'transparent', color: 'inherit', boxSizing: 'border-box',
            }}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button onClick={onClose} style={{
            padding: '8px 16px', borderRadius: '6px', border: '1px solid var(--arkham-border, #d1d5db)',
            background: 'transparent', cursor: 'pointer', fontSize: '14px', color: 'inherit',
          }}>Cancel</button>
          <button onClick={handleSubmit} disabled={saving} style={{
            padding: '8px 16px', borderRadius: '6px', border: 'none', background: '#3b82f6',
            color: 'white', cursor: 'pointer', fontWeight: 600, fontSize: '14px', opacity: saving ? 0.7 : 1,
          }}>
            {saving ? 'Adding...' : 'Add Comparator'}
          </button>
        </div>
      </div>
    </div>
  );
}

function ItemDetailView({ itemId }: { itemId: string }) {
  const { toast } = useToast();
  const [, setSearchParams] = useSearchParams();
  const [item, setItem] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        let data: Record<string, unknown> | null = null;
        try {
          data = await api.getComparator(itemId);
        } catch {
          data = await api.getIncident(itemId);
        }
        setItem(data);
      } catch (err) {
        toast.error(`Failed to load details: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [itemId, toast]);

  if (loading) return <LoadingSkeleton />;

  return (
    <div style={{ padding: '24px', maxWidth: '800px', margin: '0 auto' }}>
      <button
        onClick={() => setSearchParams({})}
        style={{
          display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '20px',
          background: 'none', border: 'none', color: '#3b82f6', cursor: 'pointer', fontWeight: 500
        }}
      >
        <Icon name="ArrowLeft" size={16} /> Back to Comparison
      </button>

      {!item ? (
        <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
          <Icon name="Search" size={48} />
          <p style={{ marginTop: '12px' }}>Item not found</p>
        </div>
      ) : (
        <div style={{ background: 'var(--arkham-bg-secondary, white)', borderRadius: '12px', padding: '32px', border: '1px solid var(--arkham-border, #e5e7eb)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{
              width: '48px', height: '48px', borderRadius: '12px', background: '#f3f4f6',
              display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#3b82f6'
            }}>
              <Icon name={item.name ? "User" : "AlertCircle"} size={24} />
            </div>
            <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0 }}>
              {String(item.name || item.description || 'Untitled Item')}
            </h1>
          </div>

          <div style={{ borderTop: '1px solid var(--arkham-border, #e5e7eb)', paddingTop: '20px' }}>
            {!!item.characteristic && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--arkham-text-muted, #9ca3af)', textTransform: 'uppercase', marginBottom: '4px' }}>Characteristic</div>
                <div style={{ fontSize: '15px' }}>{String(item.characteristic)}</div>
              </div>
            )}
            {!!item.date && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--arkham-text-muted, #9ca3af)', textTransform: 'uppercase', marginBottom: '4px' }}>Date</div>
                <div style={{ fontSize: '15px' }}>{String(item.date)}</div>
              </div>
            )}
            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--arkham-text-muted, #9ca3af)', textTransform: 'uppercase', marginBottom: '4px' }}>System ID</div>
              <div style={{ fontSize: '13px', fontFamily: 'monospace', color: 'var(--arkham-text-muted, #6b7280)' }}>{itemId}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function EmptyState({ type }: { type: TabKey }) {
  const configs = {
    incidents: { icon: 'AlertCircle', title: 'No Incidents', desc: 'Add incidents where different treatment occurred.' },
    comparators: { icon: 'Users', title: 'No Comparators', desc: 'Add colleagues or groups to compare treatment against.' },
    divergences: { icon: 'GitCompare', title: 'No Divergences', desc: 'Divergences are identified during analysis of treatment.' },
  };
  const c = configs[type];
  return (
    <div style={{ textAlign: 'center', padding: '64px 32px', color: 'var(--arkham-text-muted, #6b7280)' }}>
      <Icon name={c.icon} size={48} />
      <h3 style={{ margin: '16px 0 8px 0', fontSize: '16px', fontWeight: 600 }}>{c.title}</h3>
      <p style={{ margin: 0, fontSize: '14px' }}>{c.desc}</p>
    </div>
  );
}
