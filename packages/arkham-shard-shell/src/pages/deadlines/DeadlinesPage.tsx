import React, { useState, useEffect, useCallback } from 'react';
import { Clock, AlertTriangle, Calendar, Plus, CheckCircle, XCircle, ChevronRight } from 'lucide-react';

interface Deadline {
  id: string;
  title: string;
  deadline_date: string;
  deadline_type: string;
  status: string;
  urgency: string;
  case_type: string;
  case_reference: string;
  days_remaining: number | null;
  rule_reference: string;
}

const URGENCY_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
  critical: { color: '#dc2626', bg: '#fef2f2', label: 'CRITICAL' },
  overdue: { color: '#991b1b', bg: '#fef2f2', label: 'OVERDUE' },
  high: { color: '#ea580c', bg: '#fff7ed', label: 'HIGH' },
  medium: { color: '#d97706', bg: '#fffbeb', label: 'MEDIUM' },
  low: { color: '#16a34a', bg: '#f0fdf4', label: 'LOW' },
  future: { color: '#6b7280', bg: '#f9fafb', label: 'FUTURE' },
};

const CASE_TYPE_LABELS: Record<string, string> = {
  et: 'Employment Tribunal',
  eat: 'EAT',
  housing: 'Housing',
  jr: 'Judicial Review',
  other: 'Other',
};

export const DeadlinesPage: React.FC = () => {
  const [deadlines, setDeadlines] = useState<Deadline[]>([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<any>(null);

  const fetchData = useCallback(async () => {
    try {
      const [dlRes, statsRes] = await Promise.all([
        fetch('/api/deadlines/upcoming?days=90'),
        fetch('/api/deadlines/stats'),
      ]);
      const dlData = await dlRes.json();
      const statsData = await statsRes.json();
      setDeadlines(dlData.deadlines || []);
      setStats(statsData);
    } catch (err) {
      console.error('Failed to fetch deadlines:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
  };

  return (
    <div style={{ padding: '24px', maxWidth: '1200px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Clock size={24} /> Deadlines
          </h1>
          <p style={{ color: '#6b7280', marginTop: '4px' }}>
            Track tribunal deadlines, filing dates, and hearing schedules
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '8px 16px', background: '#f3f4f6', color: '#374151',
              border: '1px solid #e5e7eb', borderRadius: '6px', cursor: 'pointer',
            }}
          >
            <Calendar size={16} /> Export ICS
          </button>
          <button
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '8px 16px', background: '#3b82f6', color: 'white',
              border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 500,
            }}
          >
            <Plus size={16} /> Add Deadline
          </button>
        </div>
      </div>

      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '24px' }}>
          {[
            { label: 'Total', value: stats.total, color: '#6b7280' },
            { label: 'Pending', value: stats.pending, color: '#3b82f6' },
            { label: 'Breached', value: stats.breached, color: '#dc2626' },
            { label: 'Completed', value: stats.completed, color: '#16a34a' },
          ].map(s => (
            <div key={s.label} style={{
              padding: '16px', borderRadius: '8px', border: '1px solid #e5e7eb',
              background: 'var(--bg-primary, white)',
            }}>
              <div style={{ fontSize: '13px', color: '#6b7280' }}>{s.label}</div>
              <div style={{ fontSize: '28px', fontWeight: 700, color: s.color }}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: '48px', color: '#6b7280' }}>Loading deadlines...</div>
      ) : deadlines.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '48px', color: '#6b7280' }}>
          <Clock size={48} style={{ marginBottom: '12px', opacity: 0.3 }} />
          <p>No upcoming deadlines. Add your first deadline to start tracking.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {deadlines.map(dl => {
            const urg = URGENCY_CONFIG[dl.urgency] || URGENCY_CONFIG.future;
            return (
              <div
                key={dl.id}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '12px 16px', border: `1px solid ${urg.color}30`, borderRadius: '8px',
                  borderLeft: `4px solid ${urg.color}`,
                  background: 'var(--bg-primary, white)', cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
                  {dl.urgency === 'critical' || dl.urgency === 'overdue' ? (
                    <AlertTriangle size={20} style={{ color: urg.color, flexShrink: 0 }} />
                  ) : (
                    <Clock size={20} style={{ color: urg.color, flexShrink: 0 }} />
                  )}
                  <div>
                    <div style={{ fontWeight: 600 }}>{dl.title}</div>
                    <div style={{ fontSize: '13px', color: '#6b7280' }}>
                      {CASE_TYPE_LABELS[dl.case_type] || dl.case_type}
                      {dl.case_reference && ` · ${dl.case_reference}`}
                      {dl.rule_reference && ` · ${dl.rule_reference}`}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontWeight: 600, fontSize: '14px' }}>{formatDate(dl.deadline_date)}</div>
                    <div style={{ fontSize: '12px', color: urg.color, fontWeight: 600 }}>
                      {dl.days_remaining !== null && dl.days_remaining >= 0
                        ? `${dl.days_remaining} day${dl.days_remaining !== 1 ? 's' : ''} left`
                        : dl.days_remaining !== null
                          ? `${Math.abs(dl.days_remaining)} day${Math.abs(dl.days_remaining) !== 1 ? 's' : ''} overdue`
                          : ''}
                    </div>
                  </div>
                  <span style={{
                    padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 700,
                    background: urg.bg, color: urg.color,
                  }}>
                    {urg.label}
                  </span>
                  <ChevronRight size={16} style={{ color: '#9ca3af' }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
