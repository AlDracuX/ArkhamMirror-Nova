/**
 * CommsPage - Communication Thread Analysis
 *
 * Reconstructs communication threads from fragmented sources with who-knew-what-when
 * analysis and BCC detection. Handles threads, participants, gaps, and coordination flags.
 */

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';

type TabKey = 'threads' | 'participants' | 'gaps' | 'coordination';

export function CommsPage() {
  const [searchParams] = useSearchParams();
  const threadId = searchParams.get('threadId') || searchParams.get('itemId');

  if (!!threadId) {
    return <ThreadDetailView threadId={threadId} />;
  }

  return <CommsListView />;
}

// ============================================
// Main List View (Tabs)
// ============================================

function CommsListView() {
  const [activeTab, setActiveTab] = useState<TabKey>('threads');
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const tabs: { key: TabKey; label: string; icon: string }[] = [
    { key: 'threads', label: 'Threads', icon: 'MessagesSquare' },
    { key: 'participants', label: 'Participants', icon: 'Users' },
    { key: 'gaps', label: 'Gaps', icon: 'Ghost' },
    { key: 'coordination', label: 'Coordination Flags', icon: 'Flag' },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: '1400px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <Icon name="MessagesSquare" size={24} /> Communication Analysis
          </h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', marginTop: '4px', fontSize: '14px' }}>
            Reconstruct threads, detect hidden participants, and identify missing evidence
          </p>
        </div>
        <button
          onClick={() => setShowCreateDialog(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '8px 16px', borderRadius: '6px',
            background: '#3b82f6', color: 'white', border: 'none',
            fontSize: '14px', fontWeight: 600, cursor: 'pointer',
          }}
        >
          <Icon name="Plus" size={16} /> New Thread
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
      {activeTab === 'threads' && <ThreadsTab />}
      {activeTab === 'participants' && <ParticipantsTab />}
      {activeTab === 'gaps' && <GapsTab />}
      {activeTab === 'coordination' && <CoordinationTab />}

      {/* Create Dialog */}
      {showCreateDialog && (
        <CreateThreadDialog onClose={() => setShowCreateDialog(false)} />
      )}
    </div>
  );
}

// ============================================
// Threads Tab
// ============================================

function ThreadsTab() {
  const { toast } = useToast();
  const [, setSearchParams] = useSearchParams();
  const [threads, setThreads] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);

  const loadThreads = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listThreads();
      setThreads(data);
    } catch (err) {
      toast.error(`Failed to load threads: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  if (loading) return <LoadingSkeleton />;

  if (threads.length === 0) {
    return (
      <EmptyState
        icon="MessagesSquare"
        title="No communication threads"
        description="Ingest emails or documents to start thread reconstruction."
      />
    );
  }

  return (
    <div style={{ display: 'grid', gap: '12px' }}>
      {threads.map((thread) => (
        <div
          key={String(thread.id)}
          onClick={() => setSearchParams({ threadId: String(thread.id) })}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '16px', borderRadius: '8px',
            border: '1px solid var(--arkham-border, #e5e7eb)',
            background: 'var(--arkham-bg-secondary, white)',
            cursor: 'pointer',
          }}
        >
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontWeight: 600, fontSize: '15px' }}>
                {String(thread.subject || 'Untitled Thread')}
              </span>
              {!!thread.status && (
                <span style={{
                  padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 700,
                  background: String(thread.status) === 'active' ? '#dcfce7' : '#f3f4f6',
                  color: String(thread.status) === 'active' ? '#166534' : '#6b7280',
                }}>
                  {String(thread.status).toUpperCase()}
                </span>
              )}
            </div>
            <p style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)', margin: '4px 0 8px 0', lineHeight: 1.4 }}>
              {String(thread.description || 'No description provided.')}
            </p>
            <div style={{ display: 'flex', gap: '16px', fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Icon name="Users" size={12} /> {String(thread.participant_count || '0')} participants
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Icon name="Mail" size={12} /> {String(thread.message_count || '0')} messages
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Icon name="Calendar" size={12} /> {formatDate(String(thread.start_date || ''))} - {formatDate(String(thread.end_date || ''))}
              </span>
            </div>
          </div>
          <Icon name="ChevronRight" size={20} color="#9ca3af" />
        </div>
      ))}
    </div>
  );
}

// ============================================
// Participants Tab
// ============================================

function ParticipantsTab() {
  const { toast } = useToast();
  const [participants, setParticipants] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const data = await api.listParticipants();
        setParticipants(data);
      } catch (err) {
        toast.error(`Failed to load participants: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [toast]);

  if (loading) return <LoadingSkeleton />;

  if (participants.length === 0) {
    return <EmptyState icon="Users" title="No participants found" description="Participants will appear here once threads are analyzed." />;
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '12px' }}>
      {participants.map((p, idx) => (
        <div
          key={idx}
          style={{
            padding: '16px', borderRadius: '8px',
            border: '1px solid var(--arkham-border, #e5e7eb)',
            background: 'var(--arkham-bg-secondary, white)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              width: '40px', height: '40px', borderRadius: '50%',
              background: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: 700, color: '#3b82f6',
            }}>
              {String(p.name || p.address || '?').charAt(0).toUpperCase()}
            </div>
            <div>
              <div style={{ fontWeight: 600 }}>{String(p.name || 'Unknown')}</div>
              <div style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)', fontFamily: 'monospace' }}>
                {String(p.address || 'No address')}
              </div>
            </div>
          </div>
          <div style={{ marginTop: '16px', display: 'flex', gap: '12px' }}>
            <div style={{ flex: 1, textAlign: 'center', padding: '8px', background: '#f9fafb', borderRadius: '4px' }}>
              <div style={{ fontSize: '11px', color: '#9ca3af', textTransform: 'uppercase' }}>Sent</div>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>{String(p.sent_count || '0')}</div>
            </div>
            <div style={{ flex: 1, textAlign: 'center', padding: '8px', background: '#f9fafb', borderRadius: '4px' }}>
              <div style={{ fontSize: '11px', color: '#9ca3af', textTransform: 'uppercase' }}>Received</div>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>{String(p.received_count || '0')}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================
// Gaps Tab
// ============================================

function GapsTab() {
  const { toast } = useToast();
  const [gaps, setGaps] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const data = await api.listGaps();
        setGaps(data);
      } catch (err) {
        toast.error(`Failed to load gaps: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [toast]);

  if (loading) return <LoadingSkeleton />;

  if (gaps.length === 0) {
    return <EmptyState icon="Ghost" title="No gaps detected" description="Analysis hasn't detected any conspicuous silences or missing messages." />;
  }

  return (
    <div style={{ display: 'grid', gap: '12px' }}>
      {gaps.map((gap, idx) => (
        <div
          key={idx}
          style={{
            padding: '16px', borderRadius: '8px',
            border: '1px solid #fee2e2',
            background: '#fffefb',
            display: 'flex', gap: '16px',
          }}
        >
          <div style={{ color: '#ef4444' }}>
            <Icon name="AlertTriangle" size={24} />
          </div>
          <div>
            <div style={{ fontWeight: 600, color: '#991b1b', display: 'flex', alignItems: 'center', gap: '8px' }}>
              Conspicuous Silence Detected
              <span style={{ fontSize: '11px', padding: '1px 6px', background: '#fee2e2', borderRadius: '10px' }}>
                {String(gap.severity || 'low').toUpperCase()}
              </span>
            </div>
            <p style={{ fontSize: '14px', margin: '4px 0', lineHeight: 1.5 }}>
              {String(gap.description || 'Missing reply pattern identified.')}
            </p>
            <div style={{ display: 'flex', gap: '12px', marginTop: '8px', fontSize: '12px', color: '#7f1d1d' }}>
              <span>Between: {formatDate(String(gap.start_at || ''))}</span>
              <span>-</span>
              <span>{formatDate(String(gap.end_at || ''))}</span>
              {!!gap.expected_participant && (
                <span style={{ fontWeight: 600 }}>Expected: {String(gap.expected_participant)}</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================
// Coordination Flags Tab
// ============================================

function CoordinationTab() {
  const { toast } = useToast();
  const [flags, setFlags] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const data = await api.listCoordinationFlags();
        setFlags(data);
      } catch (err) {
        toast.error(`Failed to load coordination flags: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [toast]);

  if (loading) return <LoadingSkeleton />;

  if (flags.length === 0) {
    return <EmptyState icon="Flag" title="No coordination flags" description="No indicators of BCC patterns or secret forwarding chains detected." />;
  }

  return (
    <div style={{ display: 'grid', gap: '12px' }}>
      {flags.map((flag, idx) => (
        <div
          key={idx}
          style={{
            padding: '16px', borderRadius: '8px',
            border: `1px solid ${String(flag.severity) === 'high' ? '#f87171' : '#fbbf24'}`,
            background: 'var(--arkham-bg-secondary, white)',
            display: 'flex', gap: '16px',
          }}
        >
          <div style={{ color: String(flag.severity) === 'high' ? '#ef4444' : '#f59e0b' }}>
            <Icon name="Flag" size={24} />
          </div>
          <div>
            <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
              {String(flag.type || 'Flagged Coordination')}
              <span style={{
                fontSize: '11px', padding: '1px 6px',
                background: String(flag.severity) === 'high' ? '#fee2e2' : '#fef3c7',
                color: String(flag.severity) === 'high' ? '#991b1b' : '#92400e',
                borderRadius: '10px'
              }}>
                {String(flag.severity || 'medium').toUpperCase()}
              </span>
            </div>
            <p style={{ fontSize: '14px', margin: '4px 0', lineHeight: 1.5 }}>
              {String(flag.description || 'Secret communication pattern detected.')}
            </p>
            {!!flag.evidence && (
              <div style={{
                marginTop: '8px', padding: '8px', background: '#f9fafb', borderRadius: '4px',
                fontSize: '12px', border: '1px dashed #e5e7eb', fontStyle: 'italic'
              }}>
                "{String(flag.evidence)}"
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================
// Thread Detail View
// ============================================

function ThreadDetailView({ threadId }: { threadId: string }) {
  const { toast } = useToast();
  const [, setSearchParams] = useSearchParams();
  const [thread, setThread] = useState<Record<string, unknown> | null>(null);
  const [messages, setMessages] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      // Backend api.listThreads returns array, we need to find our thread
      const allThreads = await api.listThreads();
      const found = allThreads.find(t => String(t.id) === threadId);
      if (found) {
        setThread(found);
      } else {
        // Fallback to generic getItem if listThreads doesn't have it
        const generic = await api.getItem(threadId);
        setThread(generic);
      }

      const msgData = await api.listMessages(threadId);
      setMessages(msgData);
    } catch (err) {
      toast.error(`Failed to load thread details: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [threadId, toast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) return <LoadingSkeleton />;
  if (!thread) return <div style={{ padding: '24px' }}>Thread not found</div>;

  return (
    <div style={{ padding: '24px', maxWidth: '1000px' }}>
      {/* Breadcrumb */}
      <div
        onClick={() => setSearchParams({})}
        style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', cursor: 'pointer', color: '#6b7280', fontSize: '13px' }}
      >
        <Icon name="ChevronLeft" size={14} /> Back to Threads
      </div>

      {/* Header */}
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 600, margin: '0 0 8px 0' }}>
          {String(thread.subject || 'Untitled Thread')}
        </h1>
        <div style={{ display: 'flex', gap: '16px', color: '#6b7280', fontSize: '14px' }}>
          <span>{String(messages.length)} messages</span>
          <span>•</span>
          <span>Created {formatDate(String(thread.created_at || ''))}</span>
        </div>
      </div>

      {/* Message Timeline */}
      <div style={{ position: 'relative', paddingLeft: '24px' }}>
        {/* Timeline bar */}
        <div style={{
          position: 'absolute', left: '7px', top: '10px', bottom: '10px',
          width: '2px', background: '#e5e7eb'
        }} />

        {messages.length === 0 ? (
          <div style={{ color: '#9ca3af', fontStyle: 'italic', padding: '20px' }}>No messages in this thread.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            {messages.map((msg, idx) => (
              <div key={idx} style={{ position: 'relative' }}>
                {/* Timeline dot */}
                <div style={{
                  position: 'absolute', left: '-22px', top: '8px',
                  width: '12px', height: '12px', borderRadius: '50%',
                  background: 'white', border: '3px solid #3b82f6',
                }} />

                <div style={{
                  padding: '16px', borderRadius: '8px',
                  background: 'var(--arkham-bg-secondary, white)',
                  border: '1px solid var(--arkham-border, #e5e7eb)',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <div style={{ fontWeight: 600, color: '#1f2937' }}>{String(msg.from_address || 'Unknown Sender')}</div>
                    <div style={{ fontSize: '12px', color: '#9ca3af' }}>{formatDate(String(msg.sent_at || ''))}</div>
                  </div>
                  {!!msg.subject && (
                    <div style={{ fontWeight: 600, fontSize: '13px', marginBottom: '4px' }}>Sub: {String(msg.subject)}</div>
                  )}
                  <p style={{ fontSize: '14px', margin: 0, color: '#4b5563', lineHeight: 1.5 }}>
                    {String(msg.body_summary || 'No summary available.')}
                  </p>

                  {/* Recipients */}
                  <div style={{ marginTop: '12px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {(msg.to_addresses as string[] || []).map((addr, i) => (
                      <span key={i} style={{ fontSize: '10px', padding: '2px 6px', background: '#f3f4f6', borderRadius: '4px', color: '#6b7280' }}>
                        To: {addr}
                      </span>
                    ))}
                    {(msg.cc_addresses as string[] || []).map((addr, i) => (
                      <span key={i} style={{ fontSize: '10px', padding: '2px 6px', background: '#eff6ff', borderRadius: '4px', color: '#3b82f6' }}>
                        CC: {addr}
                      </span>
                    ))}
                    {(msg.bcc_addresses as string[] || []).map((addr, i) => (
                      <span key={i} style={{ fontSize: '10px', padding: '2px 6px', background: '#fee2e2', borderRadius: '4px', color: '#ef4444' }}>
                        BCC: {addr}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================
// Create Thread Dialog
// ============================================

function CreateThreadDialog({ onClose }: { onClose: () => void }) {
  const { toast } = useToast();
  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!subject) return;

    try {
      setSubmitting(true);
      await api.createThread({ subject, description });
      toast.success('Thread created successfully');
      onClose();
      // Reload page to show new thread
      window.location.reload();
    } catch (err) {
      toast.error(`Failed to create thread: ${err}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        background: 'white', borderRadius: '12px', padding: '24px',
        width: '100%', maxWidth: '500px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)',
      }}>
        <h2 style={{ margin: '0 0 20px 0', fontSize: '20px' }}>Create Reconstruction Thread</h2>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 600, marginBottom: '6px' }}>Subject</label>
            <input
              autoFocus
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="e.g., Q1 Planning Dispute"
              style={{
                width: '100%', padding: '10px', borderRadius: '6px',
                border: '1px solid #d1d5db', fontSize: '14px', boxSizing: 'border-box'
              }}
            />
          </div>
          <div style={{ marginBottom: '24px' }}>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 600, marginBottom: '6px' }}>Description (Optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Provide context for the reconstruction..."
              style={{
                width: '100%', padding: '10px', borderRadius: '6px',
                border: '1px solid #d1d5db', fontSize: '14px', minHeight: '100px',
                resize: 'vertical', boxSizing: 'border-box'
              }}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
            <button
              type="button"
              onClick={onClose}
              style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #d1d5db', background: 'white', cursor: 'pointer' }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!subject || submitting}
              style={{
                padding: '8px 16px', borderRadius: '6px', border: 'none',
                background: '#3b82f6', color: 'white', fontWeight: 600,
                cursor: (subject && !submitting) ? 'pointer' : 'not-allowed',
                opacity: (subject && !submitting) ? 1 : 0.7,
              }}
            >
              {submitting ? 'Creating...' : 'Create Thread'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ============================================
// Helpers & Sub-components
// ============================================

function EmptyState({ icon, title, description }: { icon: string; title: string; description: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '64px 24px', color: 'var(--arkham-text-muted, #6b7280)' }}>
      <Icon name={icon} size={48} color="#d1d5db" />
      <h3 style={{ marginTop: '16px', fontSize: '18px', fontWeight: 600, color: '#374151' }}>{title}</h3>
      <p style={{ marginTop: '8px', fontSize: '14px', maxWidth: '400px', margin: '8px auto 0' }}>{description}</p>
    </div>
  );
}

function formatDate(d: string): string {
  if (!d) return 'N/A';
  try {
    const date = new Date(d);
    if (isNaN(date.getTime())) return d;
    return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return d;
  }
}
