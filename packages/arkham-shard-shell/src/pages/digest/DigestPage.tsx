/**
 * DigestPage - Case Digests and Briefings
 *
 * ADHD-optimized domain-specific implementation for document analysis summaries
 * and cross-shard change aggregation.
 */

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';

type TabKey = 'briefings' | 'changelog';

export function DigestPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabKey>(
    (searchParams.get('tab') as TabKey) || 'briefings'
  );
  const briefingId = searchParams.get('briefingId');
  const projectId = searchParams.get('project_id') || searchParams.get('projectId');

  const handleTabChange = (tab: TabKey) => {
    setActiveTab(tab);
    setSearchParams(prev => {
      prev.set('tab', tab);
      return prev;
    });
  };

  if (briefingId) {
    return <BriefingDetailView briefingId={String(briefingId)} />;
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '12px', margin: 0 }}>
            <Icon name="Newspaper" size={32} /> Digest & Briefings
          </h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', marginTop: '8px', fontSize: '15px' }}>
            Daily/weekly case summaries and cross-shard activity tracking
          </p>
        </div>
        {!!projectId && <GenerateBriefingButton projectId={String(projectId)} />}
      </div>

      <div style={{ display: 'flex', gap: '4px', borderBottom: '1px solid var(--arkham-border, #e5e7eb)', marginBottom: '24px' }}>
        <button
          onClick={() => handleTabChange('briefings')}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '12px 20px', border: 'none', cursor: 'pointer',
            background: 'transparent', fontSize: '15px',
            fontWeight: activeTab === 'briefings' ? 600 : 400,
            color: activeTab === 'briefings' ? '#3b82f6' : 'var(--arkham-text-muted, #6b7280)',
            borderBottom: activeTab === 'briefings' ? '2px solid #3b82f6' : '2px solid transparent',
            marginBottom: '-1px',
            transition: 'all 0.2s ease',
          }}
        >
          <Icon name="Newspaper" size={16} /> Briefings
        </button>
        <button
          onClick={() => handleTabChange('changelog')}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '12px 20px', border: 'none', cursor: 'pointer',
            background: 'transparent', fontSize: '15px',
            fontWeight: activeTab === 'changelog' ? 600 : 400,
            color: activeTab === 'changelog' ? '#3b82f6' : 'var(--arkham-text-muted, #6b7280)',
            borderBottom: activeTab === 'changelog' ? '2px solid #3b82f6' : '2px solid transparent',
            marginBottom: '-1px',
            transition: 'all 0.2s ease',
          }}
        >
          <Icon name="History" size={16} /> Changelog
        </button>
      </div>

      {activeTab === 'briefings' && <BriefingsTab projectId={projectId ? String(projectId) : null} />}
      {activeTab === 'changelog' && <ChangelogTab projectId={projectId ? String(projectId) : null} />}
    </div>
  );
}

function BriefingsTab({ projectId }: { projectId: string | null }) {
  const { toast } = useToast();
  const [, setSearchParams] = useSearchParams();
  const [briefings, setBriefings] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  const loadBriefings = useCallback(async () => {
    if (!projectId) {
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const data = await api.listBriefings(projectId);
      const sorted = [...data].sort((a, b) => {
        const dateA = new Date(String(a.created_at || '')).getTime();
        const dateB = new Date(String(b.created_at || '')).getTime();
        return dateB - dateA;
      });
      setBriefings(sorted);
    } catch (err) {
      toast.error(`Failed to load briefings: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    loadBriefings();
  }, [loadBriefings]);

  if (loading) return <LoadingSkeleton />;

  if (!projectId) {
    return (
      <div style={{ textAlign: 'center', padding: '64px 24px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        <Icon name="Folder" size={48} style={{ opacity: 0.5 }} />
        <h3 style={{ marginTop: '16px', fontWeight: 600 }}>No Project Selected</h3>
        <p style={{ fontSize: '14px' }}>Please select a project to view its briefings.</p>
      </div>
    );
  }

  if (briefings.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '64px 24px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        <Icon name="FileText" size={48} style={{ opacity: 0.5 }} />
        <h3 style={{ marginTop: '16px', fontWeight: 600 }}>No Briefings Found</h3>
        <p style={{ fontSize: '14px' }}>Generate your first daily or weekly briefing to see case summaries here.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {briefings.map((brief) => (
        <div
          key={String(brief.id)}
          onClick={() => setSearchParams(prev => {
            prev.set('briefingId', String(brief.id));
            return prev;
          })}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '20px', borderRadius: '12px',
            border: '1px solid var(--arkham-border, #e5e7eb)',
            background: 'var(--arkham-bg-secondary, white)',
            cursor: 'pointer',
            transition: 'transform 0.1s ease, box-shadow 0.1s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = 'translateY(-2px)';
            e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.05)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = 'translateY(0)';
            e.currentTarget.style.boxShadow = 'none';
          }}
        >
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '4px' }}>
              <span style={{ fontWeight: 700, fontSize: '16px' }}>
                {String(brief.title || brief.type || 'Briefing')}
              </span>
              <PeriodBadge type={String(brief.type || 'daily')} />
            </div>
            <p style={{ margin: 0, fontSize: '14px', color: 'var(--arkham-text-muted, #6b7280)', lineHeight: 1.5, maxWidth: '800px' }}>
              {String(brief.description || brief.summary || 'Click to view full case summary...').slice(0, 160)}
              {String(brief.description || brief.summary || '').length > 160 ? '...' : ''}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)', textTransform: 'uppercase', fontWeight: 600 }}>
                Created
              </div>
              <div style={{ fontSize: '14px', fontWeight: 500 }}>
                {formatDate(String(brief.created_at || ''))}
              </div>
            </div>
            <Icon name="ChevronRight" size={20} style={{ color: '#d1d5db' }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function ChangelogTab({ projectId }: { projectId: string | null }) {
  const { toast } = useToast();
  const [changes, setChanges] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  const loadChangelog = useCallback(async () => {
    if (!projectId) {
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const data = await api.getChangelog(projectId, 50);
      setChanges(data);
    } catch (err) {
      toast.error(`Failed to load changelog: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    loadChangelog();
  }, [loadChangelog]);

  if (loading) return <LoadingSkeleton />;

  if (!projectId) {
    return (
      <div style={{ textAlign: 'center', padding: '64px 24px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        <Icon name="Folder" size={48} style={{ opacity: 0.5 }} />
        <h3 style={{ marginTop: '16px', fontWeight: 600 }}>No Project Selected</h3>
        <p style={{ fontSize: '14px' }}>Please select a project to view its activity log.</p>
      </div>
    );
  }

  if (changes.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '64px 24px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        <Icon name="Clock" size={48} style={{ opacity: 0.5 }} />
        <h3 style={{ marginTop: '16px', fontWeight: 600 }}>No Activity Logged</h3>
        <p style={{ fontSize: '14px' }}>Cross-shard activities will appear here as you work on this project.</p>
      </div>
    );
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '1px',
      background: 'var(--arkham-border, #e5e7eb)',
      borderRadius: '12px',
      overflow: 'hidden',
      border: '1px solid var(--arkham-border, #e5e7eb)',
    }}>
      {changes.map((change, idx) => (
        <div
          key={String(change.id || idx)}
          style={{
            display: 'flex', alignItems: 'center', gap: '16px',
            padding: '16px 20px',
            background: 'var(--arkham-bg-secondary, white)',
          }}
        >
          <div style={{ minWidth: '100px', fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)', fontWeight: 500 }}>
            {formatTime(String(change.timestamp || change.created_at || ''))}
          </div>
          <div style={{ width: '4px', height: '24px', background: getShardColor(String(change.shard || '')), borderRadius: '2px' }} />
          <div style={{ minWidth: '80px' }}>
            <span style={{
              padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700,
              background: `${getShardColor(String(change.shard || ''))}12`,
              color: getShardColor(String(change.shard || '')),
              textTransform: 'uppercase',
            }}>
              {String(change.shard || 'System')}
            </span>
          </div>
          <div style={{ flex: 1, fontSize: '14px', lineHeight: 1.5 }}>
            <span style={{ fontWeight: 600 }}>{String(change.actor || 'AI')}</span>
            {' '}
            {String(change.description || change.message || 'Updated project data')}
          </div>
          {!!change.entity_id && (
            <div style={{ fontSize: '11px', fontFamily: 'monospace', color: 'var(--arkham-text-muted, #9ca3af)' }}>
              id:{String(change.entity_id).slice(0, 8)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function BriefingDetailView({ briefingId }: { briefingId: string }) {
  const { toast } = useToast();
  const [, setSearchParams] = useSearchParams();
  const [briefing, setBriefing] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const data = await api.getBriefing(briefingId);
        setBriefing(data);
      } catch (err) {
        toast.error(`Failed to load briefing: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [briefingId, toast]);

  if (loading) return <LoadingSkeleton />;
  if (!briefing) return <div style={{ padding: '24px' }}>Briefing not found</div>;

  const metadata = (briefing.metadata as Record<string, unknown>) || {};
  const actionItems = (metadata.action_items || []) as Array<Record<string, unknown>>;
  const priorities = (metadata.priorities || []) as Array<Record<string, unknown>>;
  const deadlines = (metadata.deadlines || []) as Array<Record<string, unknown>>;
  const keyChanges = (metadata.key_changes || []) as Array<Record<string, unknown>>;

  return (
    <div style={{ padding: '24px', maxWidth: '1000px', margin: '0 auto' }}>
      <button
        onClick={() => setSearchParams(prev => {
          prev.delete('briefingId');
          return prev;
        })}
        style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          background: 'transparent', border: 'none', cursor: 'pointer',
          padding: '0', marginBottom: '24px', color: '#3b82f6', fontWeight: 600, fontSize: '14px',
        }}
      >
        <Icon name="ArrowLeft" size={16} /> Back to Briefings
      </button>

      <div style={{ marginBottom: '40px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <PeriodBadge type={String(briefing.type || 'daily')} large />
          <span style={{ fontSize: '14px', color: 'var(--arkham-text-muted, #6b7280)', fontWeight: 500 }}>
            Generated on {formatDate(String(briefing.created_at || ''))} at {formatTime(String(briefing.created_at || ''))}
          </span>
        </div>
        <h1 style={{ fontSize: '32px', fontWeight: 800, margin: 0, lineHeight: 1.2 }}>
          {String(briefing.title || briefing.type || 'Briefing')}
        </h1>
        <p style={{ fontSize: '18px', color: 'var(--arkham-text-muted, #4b5563)', marginTop: '12px', lineHeight: 1.6 }}>
          {String(briefing.description || briefing.summary || 'Consolidated case summary and action items.')}
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '32px', alignItems: 'start' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          <section style={{
            padding: '24px', borderRadius: '16px',
            background: 'var(--arkham-bg-secondary, white)',
            border: '2px solid #3b82f6',
            boxShadow: '0 8px 24px rgba(59, 130, 246, 0.08)',
          }}>
            <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 20px 0', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Icon name="CheckCircle" size={20} color="#3b82f6" /> Action Items
            </h2>
            {actionItems.length === 0 ? (
              <p style={{ color: 'var(--arkham-text-muted)', fontSize: '15px', fontStyle: 'italic' }}>No critical actions identified.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                {actionItems.map((item, i) => (
                  <div key={i} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                    <div style={{
                      marginTop: '6px', minWidth: '10px', height: '10px', borderRadius: '50%',
                      background: getStatusColor(String(item.priority || 'info')),
                    }} />
                    <div>
                      <div style={{ fontSize: '16px', fontWeight: 600, color: '#1f2937' }}>{String(item.title)}</div>
                      <div style={{ fontSize: '14px', color: 'var(--arkham-text-muted, #6b7280)', marginTop: '2px', lineHeight: 1.5 }}>
                        {String(item.description)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section style={{
            padding: '24px', borderRadius: '16px',
            background: 'var(--arkham-bg-secondary, white)',
            border: '1px solid var(--arkham-border, #e5e7eb)',
          }}>
            <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 20px 0', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Icon name="Zap" size={20} color="#f59e0b" /> Key Changes & Discoveries
            </h2>
            {keyChanges.length === 0 ? (
              <p style={{ color: 'var(--arkham-text-muted)', fontSize: '15px', fontStyle: 'italic' }}>No significant changes detected in this period.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                {keyChanges.map((change, i) => (
                  <div key={i} style={{ paddingLeft: '16px', borderLeft: '2px solid #e5e7eb' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                       <span style={{ fontSize: '12px', fontWeight: 700, color: getShardColor(String(change.shard || '')), textTransform: 'uppercase' }}>
                         {String(change.shard || 'System')}
                       </span>
                    </div>
                    <div style={{ fontSize: '15px', lineHeight: 1.6, color: '#374151' }}>
                      {String(change.summary)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div style={{
            padding: '20px', borderRadius: '12px',
            background: '#f9fafb',
            border: '1px solid #e5e7eb',
          }}>
            <h3 style={{ fontSize: '14px', fontWeight: 700, color: '#4b5563', textTransform: 'uppercase', marginBottom: '16px', letterSpacing: '0.05em' }}>
              Priority Ranking
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {priorities.length === 0 ? (
                <span style={{ fontSize: '13px', color: '#9ca3af' }}>No priorities set</span>
              ) : (
                priorities.map((p, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{
                      fontSize: '18px', fontWeight: 800, color: '#d1d5db', width: '24px'
                    }}>{i + 1}</div>
                    <div style={{ fontSize: '14px', fontWeight: 600, color: '#111827' }}>
                      {String(p.label || p.title)}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div style={{
            padding: '20px', borderRadius: '12px',
            background: '#fff7ed',
            border: '1px solid #fed7aa',
          }}>
            <h3 style={{ fontSize: '14px', fontWeight: 700, color: '#9a3412', textTransform: 'uppercase', marginBottom: '16px', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Icon name="AlertCircle" size={14} /> Deadline Alerts
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {deadlines.length === 0 ? (
                <span style={{ fontSize: '13px', color: '#c2410c' }}>No upcoming deadlines</span>
              ) : (
                deadlines.map((d, i) => (
                  <div key={i}>
                    <div style={{ fontSize: '13px', fontWeight: 700, color: '#9a3412' }}>{String(d.title)}</div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '2px' }}>
                      <span style={{ fontSize: '12px', color: '#c2410c' }}>{formatDate(String(d.date))}</span>
                      <span style={{
                        fontSize: '10px', fontWeight: 800, padding: '2px 6px', borderRadius: '4px',
                        background: '#fdba74', color: '#7c2d12'
                      }}>
                        {String(d.proximity || 'Soon')}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

function GenerateBriefingButton({ projectId }: { projectId: string }) {
  const { toast } = useToast();
  const [showDialog, setShowDialog] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleGenerate = async (type: string) => {
    try {
      setLoading(true);
      await api.generateBriefing({ project_id: projectId, type });
      toast.success(`${type.charAt(0).toUpperCase() + type.slice(1)} briefing generation started`);
      setShowDialog(false);
      setTimeout(() => window.location.reload(), 2000);
    } catch (err) {
      toast.error(`Failed to generate briefing: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setShowDialog(true)}
        style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          padding: '10px 20px', borderRadius: '8px', border: 'none',
          background: '#3b82f6', color: 'white', fontWeight: 600,
          cursor: 'pointer', boxShadow: '0 2px 4px rgba(59, 130, 246, 0.2)',
        }}
      >
        <Icon name="Plus" size={18} /> Generate Briefing
      </button>

      {!!showDialog && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center',
          justifyContent: 'center', zIndex: 1000,
        }}>
          <div style={{
            background: 'white', padding: '32px', borderRadius: '16px',
            width: '400px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)',
          }}>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '20px', fontWeight: 700 }}>Generate Briefing</h3>
            <p style={{ color: '#6b7280', fontSize: '14px', marginBottom: '24px' }}>
              Select the period for your automated case briefing.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <button
                disabled={loading}
                onClick={() => handleGenerate('daily')}
                style={{
                  display: 'flex', alignItems: 'center', gap: '12px', padding: '16px',
                  borderRadius: '12px', border: '1px solid #e5e7eb', background: 'white',
                  cursor: 'pointer', textAlign: 'left',
                }}
              >
                <div style={{ background: '#dbeafe', padding: '8px', borderRadius: '8px' }}>
                  <Icon name="Calendar" size={20} color="#3b82f6" />
                </div>
                <div>
                  <div style={{ fontWeight: 600 }}>Daily Briefing</div>
                  <div style={{ fontSize: '12px', color: '#6b7280' }}>Last 24 hours of activity</div>
                </div>
              </button>

              <button
                disabled={loading}
                onClick={() => handleGenerate('weekly')}
                style={{
                  display: 'flex', alignItems: 'center', gap: '12px', padding: '16px',
                  borderRadius: '12px', border: '1px solid #e5e7eb', background: 'white',
                  cursor: 'pointer', textAlign: 'left',
                }}
              >
                <div style={{ background: '#fef3c7', padding: '8px', borderRadius: '8px' }}>
                  <Icon name="CalendarDays" size={20} color="#d97706" />
                </div>
                <div>
                  <div style={{ fontWeight: 600 }}>Weekly Briefing</div>
                  <div style={{ fontSize: '12px', color: '#6b7280' }}>Last 7 days of activity</div>
                </div>
              </button>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '24px' }}>
              <button
                onClick={() => setShowDialog(false)}
                style={{
                  background: 'transparent', border: 'none', color: '#6b7280',
                  fontWeight: 600, cursor: 'pointer', padding: '8px 16px',
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}


function PeriodBadge({ type, large }: { type: string; large?: boolean }) {
  const isDaily = type.toLowerCase() === 'daily';
  return (
    <span style={{
      padding: large ? '4px 12px' : '2px 8px',
      borderRadius: large ? '12px' : '6px',
      fontSize: large ? '12px' : '10px',
      fontWeight: 800,
      textTransform: 'uppercase',
      background: isDaily ? '#dbeafe' : '#fef3c7',
      color: isDaily ? '#1e40af' : '#92400e',
      letterSpacing: '0.025em',
    }}>
      {type}
    </span>
  );
}

function getStatusColor(priority: string): string {
  switch (priority.toLowerCase()) {
    case 'urgent':
    case 'high':
    case 'red':
      return '#dc2626';
    case 'important':
    case 'medium':
    case 'amber':
    case 'warning':
      return '#d97706';
    case 'info':
    case 'low':
    case 'green':
    case 'success':
      return '#059669';
    default:
      return '#9ca3af';
  }
}

function getShardColor(shard: string): string {
  const s = shard.toLowerCase();
  if (s.includes('ach')) return '#3b82f6'; // Blue
  if (s.includes('entity') || s.includes('graph')) return '#8b5cf6'; // Purple
  if (s.includes('claim') || s.includes('contradiction')) return '#f43f5e'; // Rose
  if (s.includes('document') || s.includes('ingest')) return '#10b981'; // Emerald
  if (s.includes('ocr') || s.includes('parse')) return '#f59e0b'; // Amber
  return '#6b7280'; // Gray
}

function formatDate(d: string): string {
  if (!d) return 'N/A';
  try {
    return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return d;
  }
}

function formatTime(d: string): string {
  if (!d) return '';
  try {
    return new Date(d).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}
