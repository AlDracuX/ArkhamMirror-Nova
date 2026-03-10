import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';

type BundleStatus = 'draft' | 'compiling' | 'compiled' | 'finalized';
type DocStatus = 'agreed' | 'disputed' | 'pending';

interface Bundle {
  id: string;
  title: string;
  description: string;
  status: BundleStatus;
  created_at: string;
  updated_at: string;
  project_id?: string;
}

interface BundleVersion {
  id: string;
  version_number: number;
  created_at: string;
  total_pages: number;
  compiled_by?: string;
  change_notes?: string;
}

interface BundleDocument {
  id: string;
  title: string;
  start_page: number;
  end_page: number;
  status: DocStatus;
  metadata?: Record<string, unknown>;
}

interface IndexEntry {
  id: string;
  label: string;
  page_number: number;
  section?: string;
}

const STYLES = {
  container: {
    padding: '24px',
    maxWidth: '1200px',
    margin: '0 auto',
    color: '#1e293b',
    fontFamily: 'Inter, system-ui, sans-serif',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '32px',
  },
  title: {
    fontSize: '24px',
    fontWeight: 700,
    margin: 0,
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    letterSpacing: '-0.02em',
  },
  buttonPrimary: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '10px 20px',
    background: '#2563eb',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontWeight: 600,
    fontSize: '14px',
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
  buttonSecondary: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '10px 20px',
    background: 'white',
    color: '#475569',
    border: '1px solid #e2e8f0',
    borderRadius: '8px',
    fontWeight: 600,
    fontSize: '14px',
    cursor: 'pointer',
  },
  buttonDanger: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '10px 20px',
    background: '#ef4444',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontWeight: 600,
    fontSize: '14px',
    cursor: 'pointer',
  },
  card: {
    background: 'white',
    border: '1px solid #e2e8f0',
    borderRadius: '12px',
    padding: '20px',
    transition: 'transform 0.2s, box-shadow 0.2s',
    cursor: 'pointer',
    position: 'relative' as const,
  },
  badge: {
    padding: '4px 10px',
    borderRadius: '20px',
    fontSize: '11px',
    fontWeight: 700,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.05em',
  },
  modalOverlay: {
    position: 'fixed' as const,
    inset: 0,
    background: 'rgba(15, 23, 42, 0.75)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    backdropFilter: 'blur(4px)',
  },
  modalContent: {
    background: 'white',
    borderRadius: '16px',
    width: '500px',
    maxWidth: '90vw',
    padding: '32px',
    boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
  },
  input: {
    width: '100%',
    padding: '12px 16px',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
    fontSize: '14px',
    marginTop: '6px',
    marginBottom: '20px',
    outline: 'none',
    boxSizing: 'border-box' as const,
  },
  label: {
    fontSize: '13px',
    fontWeight: 600,
    color: '#64748b',
  },
};

function StatusBadge({ status }: { status: BundleStatus | DocStatus }) {
  const getColors = () => {
    switch (status) {
      case 'draft': return { bg: '#f1f5f9', text: '#64748b' };
      case 'compiling': return { bg: '#eff6ff', text: '#3b82f6' };
      case 'compiled': return { bg: '#ecfdf5', text: '#10b981' };
      case 'finalized': return { bg: '#f5f3ff', text: '#8b5cf6' };
      case 'agreed': return { bg: '#ecfdf5', text: '#10b981' };
      case 'disputed': return { bg: '#fef2f2', text: '#ef4444' };
      case 'pending': return { bg: '#f8fafc', text: '#94a3b8' };
      default: return { bg: '#f1f5f9', text: '#64748b' };
    }
  };

  const colors = getColors();

  return (
    <span style={{
      ...STYLES.badge,
      backgroundColor: colors.bg,
      color: colors.text,
      border: `1px solid ${colors.text}20`,
    }}>
      {String(status)}
    </span>
  );
}

export function BundlePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const itemId = searchParams.get('itemId');

  const setItemId = (id: string | null) => {
    if (id) {
      searchParams.set('itemId', id);
    } else {
      searchParams.delete('itemId');
    }
    setSearchParams(searchParams);
  };

  if (itemId) {
    return <BundleDetailView bundleId={itemId} onBack={() => setItemId(null)} />;
  }

  return <BundleListView onSelect={setItemId} />;
}

function BundleListView({ onSelect }: { onSelect: (id: string) => void }) {
  const { toast } = useToast();
  const [bundles, setBundles] = useState<Bundle[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [creating, setCreating] = useState(false);

  const loadBundles = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.listBundles();
      const mapped = (response.bundles || []).map((b: Record<string, unknown>) => ({
        id: String(b.id || b.bundle_id || ''),
        title: String(b.title || 'Untitled Bundle'),
        description: String(b.description || ''),
        status: (String(b.status || 'draft') as BundleStatus),
        created_at: String(b.created_at || ''),
        updated_at: String(b.updated_at || ''),
      }));
      setBundles(mapped);
    } catch (err) {
      toast.error(`Failed to load bundles: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadBundles();
  }, [loadBundles]);

  const handleCreate = async () => {
    if (!newTitle.trim()) {
      toast.error('Title is required');
      return;
    }
    try {
      setCreating(true);
      await api.createBundle({
        title: newTitle.trim(),
        description: newDesc.trim(),
      });
      toast.success('Bundle created successfully');
      setShowCreate(false);
      setNewTitle('');
      setNewDesc('');
      loadBundles();
    } catch (err) {
      toast.error(`Failed to create bundle: ${err}`);
    } finally {
      setCreating(false);
    }
  };

  if (loading) return <LoadingSkeleton />;

  return (
    <div style={STYLES.container}>
      <div style={STYLES.header}>
        <div>
          <h1 style={STYLES.title}>
            <Icon name="BookCopy" size={28} /> Hearing Bundles
          </h1>
          <p style={{ color: '#64748b', margin: '4px 0 0 0', fontSize: '14px' }}>
            Manage tribunal evidence bundles and versioning.
          </p>
        </div>
        <button
          style={STYLES.buttonPrimary}
          onClick={() => setShowCreate(true)}
        >
          <Icon name="Plus" size={18} /> Create Bundle
        </button>
      </div>

      {bundles.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '80px 20px',
          background: '#f8fafc',
          borderRadius: '16px',
          border: '2px dashed #e2e8f0'
        }}>
          <div style={{ color: '#94a3b8', marginBottom: '16px' }}>
            <Icon name="BookCopy" size={64} strokeWidth={1} />
          </div>
          <h3 style={{ margin: '0 0 8px 0', color: '#475569' }}>No bundles found</h3>
          <p style={{ color: '#94a3b8', margin: 0, fontSize: '14px' }}>
            Get started by creating your first hearing bundle.
          </p>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
          gap: '20px'
        }}>
          {bundles.map((bundle) => (
            <div
              key={bundle.id}
              style={STYLES.card}
              onClick={() => onSelect(bundle.id)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                <StatusBadge status={bundle.status} />
                <span style={{ fontSize: '12px', color: '#94a3b8' }}>
                  {new Date(bundle.updated_at).toLocaleDateString()}
                </span>
              </div>
              <h3 style={{ margin: '0 0 8px 0', fontSize: '18px', fontWeight: 700 }}>{bundle.title}</h3>
              <p style={{
                margin: 0,
                color: '#64748b',
                fontSize: '14px',
                lineHeight: '1.5',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
                minHeight: '42px'
              }}>
                {bundle.description || 'No description provided.'}
              </p>
              <div style={{
                marginTop: '20px',
                paddingTop: '16px',
                borderTop: '1px solid #f1f5f9',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                color: '#2563eb',
                fontSize: '13px',
                fontWeight: 600
              }}>
                Open Bundle <Icon name="ArrowRight" size={14} />
              </div>
            </div>
          ))}
        </div>
      )}

      {!!showCreate && (
        <div style={STYLES.modalOverlay} onClick={() => setShowCreate(false)}>
          <div style={STYLES.modalContent} onClick={e => e.stopPropagation()}>
            <h2 style={{ margin: '0 0 24px 0', fontSize: '20px', fontWeight: 700 }}>New Hearing Bundle</h2>

            <label style={STYLES.label}>Bundle Title</label>
            <input
              style={STYLES.input}
              placeholder="e.g. Claimant Hearing Bundle - R v S"
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              autoFocus
            />

            <label style={STYLES.label}>Description (Optional)</label>
            <textarea
              style={{ ...STYLES.input, minHeight: '100px', resize: 'vertical' }}
              placeholder="Provide context for this bundle..."
              value={newDesc}
              onChange={e => setNewDesc(e.target.value)}
            />

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button
                style={STYLES.buttonSecondary}
                onClick={() => setShowCreate(false)}
              >
                Cancel
              </button>
              <button
                style={STYLES.buttonPrimary}
                onClick={handleCreate}
                disabled={creating}
              >
                {creating ? 'Creating...' : 'Create Bundle'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function BundleDetailView({ bundleId, onBack }: { bundleId: string; onBack: () => void }) {
  const { toast } = useToast();
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [versions, setVersions] = useState<BundleVersion[]>([]);
  const [activeVersion, setActiveVersion] = useState<BundleVersion | null>(null);
  const [documents, setDocuments] = useState<BundleDocument[]>([]);
  const [indexEntries, setIndexEntries] = useState<IndexEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [compiling, setCompiling] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [viewTab, setViewTab] = useState<'documents' | 'index'>('documents');

  const loadBundleDetails = useCallback(async () => {
    try {
      setLoading(true);
      const [bundleData, versionsData] = await Promise.all([
        api.getBundle(bundleId),
        api.listVersions(bundleId),
      ]);

      const mappedBundle: Bundle = {
        id: String(bundleData.id || bundleData.bundle_id || ''),
        title: String(bundleData.title || ''),
        description: String(bundleData.description || ''),
        status: (String(bundleData.status || 'draft') as BundleStatus),
        created_at: String(bundleData.created_at || ''),
        updated_at: String(bundleData.updated_at || ''),
      };

      const mappedVersions = (versionsData.versions || []).map((v: Record<string, unknown>) => ({
        id: String(v.id || v.version_id || ''),
        version_number: Number(v.version_number || 0),
        created_at: String(v.created_at || ''),
        total_pages: Number(v.total_pages || 0),
        compiled_by: String(v.compiled_by || ''),
        change_notes: String(v.change_notes || ''),
      })).sort((a: BundleVersion, b: BundleVersion) => b.version_number - a.version_number);

      setBundle(mappedBundle);
      setVersions(mappedVersions);

      if (mappedVersions.length > 0) {
        setActiveVersion(mappedVersions[0]);
      }
    } catch (err) {
      toast.error(`Failed to load bundle details: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [bundleId, toast]);

  const loadVersionContent = useCallback(async (versionId: string) => {
    try {
      const [pagesData, indexData] = await Promise.all([
        api.getVersionPages(versionId),
        api.getVersionIndex(versionId),
      ]);

      const mappedDocs = (pagesData.pages || []).map((p: Record<string, unknown>) => ({
        id: String(p.id || p.document_id || ''),
        title: String(p.title || 'Untitled Document'),
        start_page: Number(p.start_page || 0),
        end_page: Number(p.end_page || 0),
        status: (String(p.status || 'pending') as DocStatus),
        metadata: (p.metadata as Record<string, unknown>) || {},
      }));

      const mappedIndex = (Object.entries(indexData || {})).map(([id, entry]: [string, any]) => ({
        id: String(id),
        label: String(entry.label || ''),
        page_number: Number(entry.page_number || 0),
        section: String(entry.section || ''),
      }));

      setDocuments(mappedDocs);
      setIndexEntries(mappedIndex);
    } catch (err) {
      toast.error(`Failed to load version content: ${err}`);
    }
  }, [toast]);

  useEffect(() => {
    loadBundleDetails();
  }, [loadBundleDetails]);

  useEffect(() => {
    if (activeVersion) {
      loadVersionContent(activeVersion.id);
    }
  }, [activeVersion, loadVersionContent]);

  const handleCompile = async () => {
    if (!bundle) return;
    try {
      setCompiling(true);
      toast.info('Compilation started. This may take a moment...');

      await api.compileBundle(bundle.id, {
        document_ids: documents.map(d => d.id),
        change_notes: 'Automated compilation',
      });

      toast.success('Bundle compiled successfully');
      loadBundleDetails();
    } catch (err) {
      toast.error(`Compilation failed: ${err}`);
    } finally {
      setCompiling(false);
    }
  };

  const handleDelete = async () => {
    if (!bundle) return;
    try {
      setDeleting(true);
      await api.deleteBundle(bundle.id);
      toast.success('Bundle deleted successfully');
      onBack();
    } catch (err) {
      toast.error(`Failed to delete bundle: ${err}`);
    } finally {
      setDeleting(false);
    }
  };

  if (loading) return <LoadingSkeleton />;
  if (!bundle) return <div style={STYLES.container}>Bundle not found</div>;

  return (
    <div style={STYLES.container}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px', fontSize: '14px', color: '#64748b' }}>
        <span style={{ cursor: 'pointer' }} onClick={onBack}>Bundles</span>
        <Icon name="ChevronRight" size={14} />
        <span style={{ color: '#1e293b', fontWeight: 600 }}>{bundle.title}</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '32px' }}>
        <div>
          <header style={{ ...STYLES.header, marginBottom: '24px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                <h1 style={{ ...STYLES.title, fontSize: '28px' }}>{bundle.title}</h1>
                <StatusBadge status={bundle.status} />
              </div>
              <p style={{ color: '#64748b', margin: 0, fontSize: '15px' }}>{bundle.description}</p>
            </div>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                style={STYLES.buttonSecondary}
                onClick={() => setShowDeleteConfirm(true)}
              >
                <Icon name="Trash" size={16} /> Delete
              </button>
              <button
                style={STYLES.buttonPrimary}
                onClick={handleCompile}
                disabled={compiling}
              >
                {compiling ? (
                  <>
                    <Icon name="Loader2" size={16} style={{ animation: 'spin 1s linear infinite' }} />
                    Compiling...
                  </>
                ) : (
                  <>
                    <Icon name="Play" size={16} /> Compile Bundle
                  </>
                )}
              </button>
            </div>
          </header>

          <div style={{ display: 'flex', gap: '32px', borderBottom: '1px solid #e2e8f0', marginBottom: '24px' }}>
            <button
              style={{
                background: 'none', border: 'none', padding: '12px 0', fontSize: '15px', fontWeight: 600,
                color: viewTab === 'documents' ? '#2563eb' : '#64748b',
                borderBottom: viewTab === 'documents' ? '2px solid #2563eb' : '2px solid transparent',
                cursor: 'pointer'
              }}
              onClick={() => setViewTab('documents')}
            >
              Documents ({documents.length})
            </button>
            <button
              style={{
                background: 'none', border: 'none', padding: '12px 0', fontSize: '15px', fontWeight: 600,
                color: viewTab === 'index' ? '#2563eb' : '#64748b',
                borderBottom: viewTab === 'index' ? '2px solid #2563eb' : '2px solid transparent',
                cursor: 'pointer'
              }}
              onClick={() => setViewTab('index')}
            >
              Table of Contents
            </button>
          </div>

          {viewTab === 'documents' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', background: '#e2e8f0', borderRadius: '12px', overflow: 'hidden', border: '1px solid #e2e8f0' }}>
              {documents.length === 0 ? (
                <div style={{ background: 'white', padding: '40px', textAlign: 'center', color: '#94a3b8' }}>
                  No documents in this version.
                </div>
              ) : (
                documents.map((doc, idx) => (
                  <div key={doc.id} style={{
                    background: 'white', padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                      <span style={{ color: '#94a3b8', fontSize: '13px', width: '20px' }}>{idx + 1}</span>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: '14px' }}>{doc.title}</div>
                        <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                          Pages {doc.start_page} – {doc.end_page} ({doc.end_page - doc.start_page + 1} total)
                        </div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                      <StatusBadge status={doc.status} />
                      <button style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>
                        <Icon name="MoreHorizontal" size={18} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '32px' }}>
              <h3 style={{ margin: '0 0 24px 0', fontSize: '18px' }}>Index of Evidence</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {indexEntries.length === 0 ? (
                  <p style={{ color: '#94a3b8', textAlign: 'center' }}>Index not yet generated. Compile the bundle to build the table of contents.</p>
                ) : (
                  indexEntries.map(entry => (
                    <div key={entry.id} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dotted #e2e8f0', paddingBottom: '4px' }}>
                      <span style={{ background: 'white', paddingRight: '8px' }}>{entry.label}</span>
                      <span style={{ background: 'white', paddingLeft: '8px', fontWeight: 600, fontFamily: 'monospace' }}>
                        {entry.page_number}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div style={{ background: '#f8fafc', borderRadius: '16px', border: '1px solid #e2e8f0', padding: '24px' }}>
            <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Icon name="History" size={18} /> Version History
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {versions.length === 0 ? (
                <div style={{ fontSize: '13px', color: '#94a3b8', textAlign: 'center', padding: '20px 0' }}>
                  No versions compiled yet.
                </div>
              ) : (
                versions.map((v) => (
                  <div
                    key={v.id}
                    onClick={() => setActiveVersion(v)}
                    style={{
                      padding: '12px',
                      borderRadius: '8px',
                      background: activeVersion?.id === v.id ? 'white' : 'transparent',
                      border: activeVersion?.id === v.id ? '1px solid #3b82f6' : '1px solid transparent',
                      boxShadow: activeVersion?.id === v.id ? '0 4px 6px -1px rgba(0, 0, 0, 0.1)' : 'none',
                      cursor: 'pointer'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                      <span style={{ fontWeight: 700, fontSize: '14px' }}>v{v.version_number}</span>
                      <span style={{ fontSize: '11px', color: '#64748b' }}>
                        {new Date(v.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', color: '#64748b' }}>
                      {v.total_pages} pages • {v.compiled_by || 'System'}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div style={{ background: '#fffbeb', borderRadius: '16px', border: '1px solid #fde68a', padding: '20px' }}>
            <h4 style={{ margin: '0 0 8px 0', fontSize: '14px', fontWeight: 700, color: '#92400e', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Icon name="Info" size={14} /> Drafting Tip
            </h4>
            <p style={{ margin: 0, fontSize: '13px', color: '#b45309', lineHeight: '1.5' }}>
              Ensure all "Disputed" documents have clear reasons noted in the metadata before finalization for the judge.
            </p>
          </div>
        </div>
      </div>

      {!!showDeleteConfirm && (
        <div style={STYLES.modalOverlay} onClick={() => setShowDeleteConfirm(false)}>
          <div style={STYLES.modalContent} onClick={e => e.stopPropagation()}>
            <div style={{ color: '#ef4444', marginBottom: '16px' }}>
              <Icon name="AlertTriangle" size={48} />
            </div>
            <h2 style={{ margin: '0 0 12px 0', fontSize: '20px', fontWeight: 700 }}>Delete Bundle?</h2>
            <p style={{ color: '#64748b', fontSize: '14px', marginBottom: '24px', lineHeight: '1.5' }}>
              Are you sure you want to delete <strong>{bundle.title}</strong>? This action cannot be undone and all version history will be lost.
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button
                style={STYLES.buttonSecondary}
                onClick={() => setShowDeleteConfirm(false)}
              >
                Cancel
              </button>
              <button
                style={STYLES.buttonDanger}
                onClick={handleDelete}
                disabled={deleting}
              >
                {deleting ? 'Deleting...' : 'Delete Permanently'}
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
