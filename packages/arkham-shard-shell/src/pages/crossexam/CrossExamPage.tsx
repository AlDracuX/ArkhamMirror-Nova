import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';

export function CrossExamPage() {
  const [searchParams] = useSearchParams();
  const treeId = searchParams.get('treeId');
  const impeachmentId = searchParams.get('impeachmentId');

  if (treeId) {
    return <TreeDetailView treeId={treeId} />;
  }

  if (impeachmentId) {
    return <ImpeachmentDetailView impeachmentId={impeachmentId} />;
  }

  return <CrossExamDashboard />;
}

function CrossExamDashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'trees';

  const setTab = (tab: string) => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set('tab', tab);
    setSearchParams(newParams);
  };

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '12px', margin: 0 }}>
            <Icon name="Swords" size={28} /> Cross-Examination
          </h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', marginTop: '4px', fontSize: '14px' }}>
            Build question trees, detect impeachments, and score damage potential
          </p>
        </div>
      </header>

      <div style={{ display: 'flex', gap: '2px', borderBottom: '1px solid var(--arkham-border, #e5e7eb)', marginBottom: '24px' }}>
        {[
          { key: 'trees', label: 'Question Trees', icon: 'GitBranch' },
          { key: 'impeachments', label: 'Impeachments', icon: 'Zap' },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setTab(tab.key)}
            style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '12px 20px', border: 'none', cursor: 'pointer',
              background: 'transparent', fontSize: '14px', fontWeight: activeTab === tab.key ? 600 : 400,
              color: activeTab === tab.key ? '#3b82f6' : 'var(--arkham-text-muted, #6b7280)',
              borderBottom: activeTab === tab.key ? '2px solid #3b82f6' : '2px solid transparent',
              marginBottom: '-1px',
              transition: 'all 0.15s ease',
            }}
          >
            <Icon name={tab.icon} size={16} /> {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'trees' ? <TreeListView /> : <ImpeachmentListView />}
    </div>
  );
}

function TreeListView() {
  const { toast } = useToast();
  const [trees, setTrees] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showGenerateDialog, setShowGenerateDialog] = useState(false);

  const loadTrees = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listTrees();
      setTrees(data.trees);
    } catch (err) {
      toast.error(`Failed to load trees: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadTrees();
  }, [loadTrees]);

  if (loading) return <LoadingSkeleton />;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginBottom: '20px' }}>
        <button
          onClick={() => setShowGenerateDialog(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            padding: '8px 16px', background: 'var(--arkham-bg-secondary, white)', color: '#3b82f6',
            border: '1px solid #3b82f6', borderRadius: '6px', cursor: 'pointer', fontWeight: 500,
          }}
        >
          <Icon name="Sparkles" size={16} /> Generate Tree
        </button>
        <button
          onClick={() => setShowCreateDialog(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            padding: '8px 16px', background: '#3b82f6', color: 'white',
            border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 500,
          }}
        >
          <Icon name="Plus" size={16} /> New Tree
        </button>
      </div>

      {trees.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '64px', color: 'var(--arkham-text-muted, #6b7280)', background: 'var(--arkham-bg-secondary, #f9fafb)', borderRadius: '12px', border: '1px dashed var(--arkham-border, #e5e7eb)' }}>
          <Icon name="GitBranch" size={48} />
          <p style={{ marginTop: '16px', fontSize: '16px' }}>No question trees found.</p>
          <p style={{ fontSize: '14px' }}>Create or generate a tree to start witness preparation.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '16px' }}>
          {trees.map((tree) => (
            <TreeCard key={String(tree.id)} tree={tree} />
          ))}
        </div>
      )}

      {showCreateDialog && (
        <CreateTreeDialog
          onClose={() => setShowCreateDialog(false)}
          onCreated={() => { setShowCreateDialog(false); loadTrees(); }}
        />
      )}

      {showGenerateDialog && (
        <GenerateTreeDialog
          onClose={() => setShowGenerateDialog(false)}
          onGenerated={() => { setShowGenerateDialog(false); loadTrees(); }}
        />
      )}
    </div>
  );
}

function TreeCard({ tree }: { tree: Record<string, unknown> }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const damageScore = Number(tree.damage_score || 0);

  const getDamageColor = (score: number) => {
    if (score >= 8) return '#ef4444';
    if (score >= 4) return '#f59e0b';
    return '#10b981';
  };

  const handleClick = () => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set('treeId', String(tree.id));
    setSearchParams(newParams);
  };

  return (
    <div
      onClick={handleClick}
      style={{
        padding: '20px', borderRadius: '12px', border: '1px solid var(--arkham-border, #e5e7eb)',
        background: 'var(--arkham-bg-secondary, white)', cursor: 'pointer',
        transition: 'all 0.15s ease-in-out',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-2px)';
        e.currentTarget.style.boxShadow = '0 10px 15px -3px rgba(0, 0, 0, 0.1)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
        <div style={{ flex: 1 }}>
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--arkham-text-primary)' }}>{String(tree.title)}</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)', marginTop: '4px' }}>
            <Icon name="User" size={14} /> {String(tree.witness_name || tree.witness_id || 'Unknown Witness')}
          </div>
        </div>
        <div style={{
          padding: '4px 8px', borderRadius: '6px', background: `${getDamageColor(damageScore)}15`,
          color: getDamageColor(damageScore), fontSize: '12px', fontWeight: 700,
          border: `1px solid ${getDamageColor(damageScore)}30`, whiteSpace: 'nowrap'
        }}>
          Score: {damageScore}/10
        </div>
      </div>

      <p style={{
        fontSize: '14px', color: 'var(--arkham-text-muted, #6b7280)', margin: '0 0 16px 0',
        height: '40px', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical'
      }}>
        {String(tree.description || 'No description available')}
      </p>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', borderTop: '1px solid var(--arkham-border, #f3f4f6)', paddingTop: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: 'var(--arkham-text-muted, #6b7280)' }}>
          <Icon name="HelpCircle" size={14} /> {String(tree.question_count || 0)} Questions
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: 'var(--arkham-text-muted, #6b7280)' }}>
          <Icon name="Zap" size={14} /> {String(tree.impeachment_count || 0)} Impeachments
        </div>
      </div>
    </div>
  );
}

function TreeDetailView({ treeId }: { treeId: string }) {
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [nodes, setNodes] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  const loadNodes = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getTreeNodes(treeId);
      setNodes(data.nodes);
    } catch (err) {
      toast.error(`Failed to load tree nodes: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [treeId, toast]);

  useEffect(() => {
    loadNodes();
  }, [loadNodes]);

  const goBack = () => {
    const newParams = new URLSearchParams(searchParams);
    newParams.delete('treeId');
    setSearchParams(newParams);
  };

  if (loading) return <LoadingSkeleton />;

  const buildTree = (parentId: string | null = null): Record<string, unknown>[] => {
    return nodes
      .filter(n => (parentId === null ? !n.parent_id : String(n.parent_id) === parentId))
      .map(n => ({
        ...n,
        children: buildTree(String(n.id))
      }));
  };

  const hierarchicalNodes = buildTree();

  return (
    <div style={{ padding: '24px', maxWidth: '1000px', margin: '0 auto' }}>
      <button
        onClick={goBack}
        style={{
          display: 'flex', alignItems: 'center', gap: '6px', background: 'transparent',
          border: 'none', color: 'var(--arkham-text-muted, #6b7280)', cursor: 'pointer',
          padding: '0', marginBottom: '20px', fontSize: '14px'
        }}
      >
        <Icon name="ArrowLeft" size={16} /> Back to Question Trees
      </button>

      <div style={{ marginBottom: '32px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, margin: '0 0 8px 0' }}>Question Tree Detail</h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', margin: 0, fontSize: '15px' }}>
            Witness: <strong style={{ color: 'var(--arkham-text-primary)' }}>{String(nodes[0]?.witness_name || 'Witness')}</strong>
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
           <button style={{ padding: '8px 14px', borderRadius: '6px', border: '1px solid var(--arkham-border)', background: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
             <Icon name="Download" size={14} /> Export PDF
           </button>
           <button style={{ padding: '8px 14px', borderRadius: '6px', border: 'none', background: '#3b82f6', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: 500 }}>
             <Icon name="Plus" size={14} /> Add Question
           </button>
        </div>
      </div>

      {hierarchicalNodes.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '64px', color: 'var(--arkham-text-muted, #6b7280)', background: 'var(--arkham-bg-secondary)', borderRadius: '12px' }}>
          <Icon name="GitBranch" size={48} />
          <p style={{ marginTop: '16px' }}>No nodes in this tree yet.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {hierarchicalNodes.map((node, i) => (
            <QuestionNode key={String(node.id || i)} node={node} depth={0} />
          ))}
        </div>
      )}
    </div>
  );
}

function QuestionNode({ node, depth }: { node: Record<string, unknown>; depth: number }) {
  const damage = Number(node.damage_potential || 0);
  const children = (node.children || []) as Record<string, unknown>[];

  const getDamageColor = (score: number) => {
    if (score >= 8) return '#ef4444';
    if (score >= 4) return '#f59e0b';
    return '#10b981';
  };

  const color = getDamageColor(damage);

  return (
    <div style={{ marginLeft: depth * 28 }}>
      <div style={{
        padding: '16px', borderRadius: '10px', border: '1px solid var(--arkham-border, #e5e7eb)',
        background: 'var(--arkham-bg-secondary, white)', borderLeft: `4px solid ${color}`,
        position: 'relative',
        boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
      }}>
        {depth > 0 && (
          <div style={{
            position: 'absolute', left: '-20px', top: '24px', width: '20px', height: '1px',
            background: 'var(--arkham-border, #e5e7eb)'
          }} />
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color, display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Icon name="Target" size={12} /> Damage Potential: {damage}/10
          </div>
          <div style={{ display: 'flex', gap: '4px' }}>
            <button style={{ background: 'transparent', border: 'none', color: 'var(--arkham-text-muted, #6b7280)', cursor: 'pointer', padding: '2px' }}>
              <Icon name="Edit2" size={14} />
            </button>
            <button style={{ background: 'transparent', border: 'none', color: 'var(--arkham-text-muted, #6b7280)', cursor: 'pointer', padding: '2px' }}>
              <Icon name="Trash2" size={14} />
            </button>
          </div>
        </div>

        <div style={{ fontWeight: 600, fontSize: '15px', marginBottom: '12px', color: 'var(--arkham-text-primary)' }}>
          {String(node.question_text)}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <div style={{ padding: '10px', background: '#f0fdf4', borderRadius: '8px', border: '1px solid #dcfce7' }}>
            <div style={{ fontSize: '10px', fontWeight: 700, color: '#166534', textTransform: 'uppercase', marginBottom: '4px', letterSpacing: '0.05em' }}>Expected Answer</div>
            <div style={{ fontSize: '13px', color: '#166534' }}>{String(node.expected_answer || 'None specified')}</div>
          </div>
          <div style={{ padding: '10px', background: '#fef2f2', borderRadius: '8px', border: '1px solid #fee2e2' }}>
            <div style={{ fontSize: '10px', fontWeight: 700, color: '#991b1b', textTransform: 'uppercase', marginBottom: '4px', letterSpacing: '0.05em' }}>Alternative Answer</div>
            <div style={{ fontSize: '13px', color: '#991b1b' }}>{String(node.alternative_answer || 'None specified')}</div>
          </div>
        </div>
      </div>

      {children.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '12px' }}>
          {children.map((child, i) => (
            <QuestionNode key={String(child.id || i)} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function ImpeachmentListView() {
  const { toast } = useToast();
  const [impeachments, setImpeachments] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  const loadImpeachments = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listImpeachments();
      setImpeachments(data.impeachments);
    } catch (err) {
      toast.error(`Failed to load impeachments: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadImpeachments();
  }, [loadImpeachments]);

  if (loading) return <LoadingSkeleton />;

  return (
    <div>
      {impeachments.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '64px', color: 'var(--arkham-text-muted, #6b7280)', background: 'var(--arkham-bg-secondary, #f9fafb)', borderRadius: '12px', border: '1px dashed var(--arkham-border, #e5e7eb)' }}>
          <Icon name="Zap" size={48} />
          <p style={{ marginTop: '16px', fontSize: '16px' }}>No impeachments detected.</p>
          <p style={{ fontSize: '14px' }}>Analyze documents to find witness contradictions.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {impeachments.map((imp) => (
            <ImpeachmentCard key={String(imp.id)} impeachment={imp} />
          ))}
        </div>
      )}
    </div>
  );
}

function ImpeachmentCard({ impeachment }: { impeachment: Record<string, unknown> }) {
  const [searchParams, setSearchParams] = useSearchParams();

  const handleClick = () => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set('impeachmentId', String(impeachment.id));
    setSearchParams(newParams);
  };

  return (
    <div
      onClick={handleClick}
      style={{
        padding: '16px', borderRadius: '10px', border: '1px solid var(--arkham-border, #e5e7eb)',
        background: 'var(--arkham-bg-secondary, white)', cursor: 'pointer',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        transition: 'background 0.1s ease',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--arkham-bg-tertiary, #f9fafb)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--arkham-bg-secondary, white)'; }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{
          width: '40px', height: '40px', borderRadius: '8px', background: '#fef3c7',
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#d97706'
        }}>
          <Icon name="AlertTriangle" size={20} />
        </div>
        <div>
          <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--arkham-text-primary)' }}>{String(impeachment.title)}</h4>
          <p style={{ margin: '2px 0 0 0', fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)' }}>
            Witness: {String(impeachment.witness_name || 'Unknown')}
          </p>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
         <div style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #6b7280)', display: 'flex', alignItems: 'center', gap: '4px' }}>
          <Icon name="Layers" size={14} /> {String((impeachment.steps as Array<unknown>)?.length || 0)} steps
        </div>
        <Icon name="ChevronRight" size={18} color="var(--arkham-text-muted)" />
      </div>
    </div>
  );
}

function ImpeachmentDetailView({ impeachmentId }: { impeachmentId: string }) {
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [impeachment, setImpeachment] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const data = await api.listImpeachments();
        const found = data.impeachments.find(i => String(i.id) === impeachmentId);
        setImpeachment(found || null);
      } catch (err) {
        toast.error(`Failed to load impeachment: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [impeachmentId, toast]);

  const goBack = () => {
    const newParams = new URLSearchParams(searchParams);
    newParams.delete('impeachmentId');
    setSearchParams(newParams);
  };

  if (loading) return <LoadingSkeleton />;
  if (!impeachment) return <div style={{ padding: '24px' }}>Impeachment not found</div>;

  const steps = (impeachment.steps || []) as Record<string, unknown>[];

  return (
    <div style={{ padding: '24px', maxWidth: '900px', margin: '0 auto' }}>
      <button
        onClick={goBack}
        style={{
          display: 'flex', alignItems: 'center', gap: '6px', background: 'transparent',
          border: 'none', color: 'var(--arkham-text-muted, #6b7280)', cursor: 'pointer',
          padding: '0', marginBottom: '20px', fontSize: '14px'
        }}
      >
        <Icon name="ArrowLeft" size={16} /> Back to Dashboard
      </button>

      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 600, margin: '0 0 8px 0', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Icon name="Zap" size={26} color="#d97706" /> {String(impeachment.title)}
        </h1>
        <p style={{ color: 'var(--arkham-text-muted, #6b7280)', margin: 0, fontSize: '15px' }}>
          Witness: <strong style={{ color: 'var(--arkham-text-primary)' }}>{String(impeachment.witness_name || 'Unknown')}</strong> | Conflict detected via Statement vs Document
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 600, margin: 0, borderBottom: '1px solid var(--arkham-border)', paddingBottom: '8px' }}>
          Impeachment Sequence
        </h3>

        {steps.length === 0 ? (
          <p style={{ color: 'var(--arkham-text-muted)', textAlign: 'center', padding: '32px' }}>No sequence steps defined for this impeachment.</p>
        ) : (
          <div style={{ position: 'relative', paddingLeft: '32px' }}>
            <div style={{ position: 'absolute', left: '15px', top: '10px', bottom: '10px', width: '2px', background: 'var(--arkham-border, #e5e7eb)' }} />

            {steps.map((step, i) => (
              <div key={i} style={{ marginBottom: '24px', position: 'relative' }}>
                <div style={{
                  position: 'absolute', left: '-25px', top: '4px', width: '16px', height: '16px',
                  borderRadius: '50%', background: '#3b82f6', border: '3px solid white', boxShadow: '0 0 0 2px #3b82f6',
                  zIndex: 2
                }} />

                <div style={{
                  padding: '16px', borderRadius: '12px', border: '1px solid var(--arkham-border, #e5e7eb)',
                  background: 'var(--arkham-bg-secondary, white)', boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)'
                }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--arkham-text-muted, #6b7280)', marginBottom: '8px', letterSpacing: '0.05em' }}>
                    Step {i + 1}: {String(step.action || 'Inquiry')}
                  </div>
                  <div style={{ fontWeight: 600, fontSize: '15px', marginBottom: '12px', color: 'var(--arkham-text-primary)' }}>{String(step.description)}</div>

                  {!!step.conflict && (
                    <div style={{
                      marginTop: '12px', padding: '16px', background: '#fff7ed', borderRadius: '10px',
                      border: '1px solid #ffedd5', boxShadow: 'inset 0 1px 2px 0 rgba(0,0,0,0.05)'
                    }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                        <div>
                          <div style={{ fontSize: '11px', fontWeight: 700, color: '#9a3412', textTransform: 'uppercase', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <Icon name="MessageSquare" size={12} /> Statement Claim
                          </div>
                          <div style={{ fontSize: '13px', fontStyle: 'italic', lineHeight: 1.5, color: '#7c2d12' }}>
                            "{String((step.conflict as Record<string, unknown>).statement_text)}"
                          </div>
                        </div>
                        <div style={{ borderLeft: '1px solid #ffedd5', paddingLeft: '16px' }}>
                          <div style={{ fontSize: '11px', fontWeight: 700, color: '#9a3412', textTransform: 'uppercase', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <Icon name="FileText" size={12} /> Document Evidence
                          </div>
                          <div style={{ fontSize: '13px', fontStyle: 'italic', lineHeight: 1.5, color: '#7c2d12' }}>
                            "{String((step.conflict as Record<string, unknown>).document_text)}"
                          </div>
                          <div style={{ fontSize: '11px', color: '#c2410c', marginTop: '8px', fontWeight: 500 }}>
                            Reference: {String((step.conflict as Record<string, unknown>).reference)}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CreateTreeDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { toast } = useToast();
  const [title, setTitle] = useState('');
  const [witnessId, setWitnessId] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    if (!title.trim() || !witnessId.trim()) {
      toast.error('Title and Witness are required');
      return;
    }
    try {
      setSaving(true);
      await api.createTree({
        title: title.trim(),
        witness_id: witnessId.trim(),
        description: description.trim(),
      });
      toast.success('Question tree created');
      onCreated();
    } catch (err) {
      toast.error(`Failed to create: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ background: 'var(--arkham-bg-primary, white)', padding: '24px', borderRadius: '12px', width: '480px', maxWidth: '90vw', border: '1px solid var(--arkham-border)' }}>
        <h2 style={{ margin: '0 0 20px 0', fontSize: '18px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Icon name="GitBranch" size={20} /> Create Question Tree
        </h2>

        <label style={{ display: 'block', marginBottom: '16px' }}>
          <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Witness</span>
          <input
            value={witnessId} onChange={e => setWitnessId(e.target.value)}
            placeholder="Search or enter witness name..."
            style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid var(--arkham-border)', background: 'var(--arkham-bg-primary)', boxSizing: 'border-box', outline: 'none' }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: '16px' }}>
          <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Title</span>
          <input
            value={title} onChange={e => setTitle(e.target.value)}
            placeholder="e.g. Cross-examination on Incident A"
            style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid var(--arkham-border)', background: 'var(--arkham-bg-primary)', boxSizing: 'border-box', outline: 'none' }}
          />
        </label>

        <label style={{ display: 'block', marginBottom: '24px' }}>
          <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Strategy Description</span>
          <textarea
            value={description} onChange={e => setDescription(e.target.value)}
            rows={3} placeholder="Goal of this line of questioning..."
            style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid var(--arkham-border)', background: 'var(--arkham-bg-primary)', boxSizing: 'border-box', resize: 'vertical', outline: 'none' }}
          />
        </label>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button onClick={onClose} style={{ padding: '10px 16px', background: 'transparent', border: '1px solid var(--arkham-border)', borderRadius: '6px', cursor: 'pointer', fontSize: '14px' }}>Cancel</button>
          <button onClick={handleCreate} disabled={saving} style={{ padding: '10px 20px', background: '#3b82f6', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600, fontSize: '14px', opacity: saving ? 0.7 : 1 }}>
            {saving ? 'Creating...' : 'Create Tree'}
          </button>
        </div>
      </div>
    </div>
  );
}

function GenerateTreeDialog({ onClose, onGenerated }: { onClose: () => void; onGenerated: () => void }) {
  const { toast } = useToast();
  const [witnessId, setWitnessId] = useState('');
  const [generating, setGenerating] = useState(false);

  const handleGenerate = async () => {
    if (!witnessId.trim()) { toast.error('Witness selection is required'); return; }
    try {
      setGenerating(true);
      await api.generateQuestionTree(witnessId.trim(), 'default-project');
      toast.success('AI generation task submitted');
      onGenerated();
    } catch (err) {
      toast.error(`Failed to generate: ${err}`);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ background: 'var(--arkham-bg-primary, white)', padding: '24px', borderRadius: '12px', width: '480px', maxWidth: '90vw', border: '1px solid var(--arkham-border)' }}>
        <h2 style={{ margin: '0 0 12px 0', fontSize: '18px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Icon name="Sparkles" size={20} color="#3b82f6" /> AI Tree Generation
        </h2>
        <p style={{ fontSize: '14px', color: 'var(--arkham-text-muted)', marginBottom: '20px', lineHeight: 1.5 }}>
          Our AI analyst will examine all case documents related to the selected witness to identify inconsistencies and build a damaging line of questioning.
        </p>

        <label style={{ display: 'block', marginBottom: '24px' }}>
          <span style={{ fontSize: '13px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Select Witness</span>
          <input
            value={witnessId} onChange={e => setWitnessId(e.target.value)}
            placeholder="Enter witness name..."
            style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid var(--arkham-border)', background: 'var(--arkham-bg-primary)', boxSizing: 'border-box', outline: 'none' }}
          />
        </label>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button onClick={onClose} style={{ padding: '10px 16px', background: 'transparent', border: '1px solid var(--arkham-border)', borderRadius: '6px', cursor: 'pointer', fontSize: '14px' }}>Cancel</button>
          <button onClick={handleGenerate} disabled={generating} style={{ padding: '10px 20px', background: '#3b82f6', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600, fontSize: '14px', opacity: generating ? 0.7 : 1 }}>
            {generating ? 'Generating...' : 'Start AI Generation'}
          </button>
        </div>
      </div>
    </div>
  );
}
