/**
 * StrategistPage - AI Adversarial Modeler
 *
 * Predicts respondent arguments, red-teams submissions, and generates
 * counter-argument briefings. Features tabbed views for Predictions,
 * Red Team Reports, and Tactical Models.
 */

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';

type TabKey = 'predictions' | 'red-team' | 'tactical';

interface Prediction {
  id: string;
  claim_text: string;
  respondent_context?: string;
  predicted_arguments: Array<{
    argument: string;
    counter_argument: string;
    probability: number;
    severity: 'critical' | 'high' | 'medium' | 'low';
  }>;
  created_at: string;
}

interface RedTeamReport {
  id: string;
  title: string;
  weakness_count: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  summary: string;
  created_at: string;
}

interface TacticalModel {
  id: string;
  title: string;
  predicted_moves: Array<{
    move: string;
    timing: string;
    impact: string;
  }>;
  created_at: string;
}

export function StrategistPage() {
  const [searchParams] = useSearchParams();
  const itemId = searchParams.get('itemId') || searchParams.get('id');

  if (!!itemId) {
    return <StrategistDetailView itemId={String(itemId)} />;
  }

  return <StrategistListView />;
}

// ============================================
// List View — Tabbed: Predictions | Red Team | Tactical
// ============================================

function StrategistListView() {
  const [activeTab, setActiveTab] = useState<TabKey>('predictions');
  const [showGenerate, setShowGenerate] = useState(false);

  const tabs: { key: TabKey; label: string; icon: string }[] = [
    { key: 'predictions', label: 'Predictions', icon: 'BrainCircuit' },
    { key: 'red-team', label: 'Red Team Reports', icon: 'ShieldAlert' },
    { key: 'tactical', label: 'Tactical Models', icon: 'Network' },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: '1200px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <Icon name="Zap" size={24} /> Strategist
          </h1>
          <p style={{ color: '#6b7280', marginTop: '4px', fontSize: '14px' }}>
            AI adversarial modeling: Predict arguments, red-team submissions, and map procedural moves.
          </p>
        </div>
        <button
          onClick={() => setShowGenerate(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '10px 16px', borderRadius: '8px',
            background: '#2563eb', color: 'white',
            border: 'none', fontWeight: 600, cursor: 'pointer',
          }}
        >
          <Icon name="Plus" size={16} /> New Prediction
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '2px', borderBottom: '1px solid #e5e7eb', marginBottom: '20px' }}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '10px 16px', border: 'none', cursor: 'pointer',
              background: 'transparent', fontSize: '14px',
              fontWeight: activeTab === tab.key ? 600 : 400,
              color: activeTab === tab.key ? '#2563eb' : '#6b7280',
              borderBottom: activeTab === tab.key ? '2px solid #2563eb' : '2px solid transparent',
              marginBottom: '-1px',
            }}
          >
            <Icon name={tab.icon} size={14} /> {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'predictions' && <PredictionsTab />}
      {activeTab === 'red-team' && <RedTeamTab />}
      {activeTab === 'tactical' && <TacticalTab />}

      {/* Generate Dialog */}
      {showGenerate && (
        <GeneratePredictionDialog onClose={() => setShowGenerate(false)} />
      )}
    </div>
  );
}

// ============================================
// Predictions Tab
// ============================================

function PredictionsTab() {
  const { toast } = useToast();
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [loading, setLoading] = useState(true);

  const loadPredictions = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listItems({ type: 'prediction' });
      // Map generic items to Prediction interface
      const mapped = (data.items || []).map(item => ({
        id: String(item.id),
        claim_text: String(item.title || ''),
        respondent_context: String(item.description || ''),
        predicted_arguments: ((item.metadata as Record<string, unknown> | undefined)?.predicted_arguments as Prediction['predicted_arguments']) || [],
        created_at: String(item.created_at || ''),
      }));
      setPredictions(mapped);
    } catch (err) {
      toast.error(`Failed to load predictions: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadPredictions();
  }, [loadPredictions]);

  if (loading) return <LoadingSkeleton />;

  if (predictions.length === 0) {
    return <EmptyState icon="BrainCircuit" label="No predictions yet" description="Generate an adversarial prediction to see potential respondent arguments." />;
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(450px, 1fr))', gap: '20px' }}>
      {predictions.map((pred) => (
        <PredictionCard key={pred.id} prediction={pred} />
      ))}
    </div>
  );
}

function PredictionCard({ prediction }: { prediction: Prediction }) {
  return (
    <div
      onClick={() => window.history.pushState(null, '', `?itemId=${prediction.id}`)}
      style={{
        padding: '20px', borderRadius: '12px',
        border: '1px solid #e5e7eb',
        background: 'white', cursor: 'pointer',
        transition: 'box-shadow 0.2s',
      }}
      onMouseOver={(e) => e.currentTarget.style.boxShadow = '0 4px 6px -1px rgba(0, 0, 0, 0.1)'}
      onMouseOut={(e) => e.currentTarget.style.boxShadow = 'none'}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
        <div style={{ fontSize: '12px', color: '#6b7280', fontWeight: 600, textTransform: 'uppercase' }}>
          Prediction • {formatDate(prediction.created_at)}
        </div>
        <Icon name="ChevronRight" size={16} />
      </div>
      <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 600, color: '#111827' }}>
        {prediction.claim_text}
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {prediction.predicted_arguments.slice(0, 2).map((arg, i) => (
          <div key={i} style={{ padding: '12px', borderRadius: '8px', background: '#f9fafb', borderLeft: `4px solid ${getSeverityColor(arg.severity)}` }}>
            <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '4px', color: '#374151' }}>
              Predicted: {arg.argument}
            </div>
            <div style={{ fontSize: '12px', color: '#6b7280', fontStyle: 'italic' }}>
              Counter: {arg.counter_argument}
            </div>
          </div>
        ))}
        {prediction.predicted_arguments.length > 2 && (
          <div style={{ fontSize: '12px', color: '#2563eb', fontWeight: 500 }}>
            + {prediction.predicted_arguments.length - 2} more predicted arguments
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================
// Red Team Tab
// ============================================

function RedTeamTab() {
  const { toast } = useToast();
  const [reports, setReports] = useState<RedTeamReport[]>([]);
  const [loading, setLoading] = useState(true);

  const loadReports = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams(window.location.search);
      const projectId = params.get('project_id') || params.get('projectId') || 'default';
      const data = await api.listReports(projectId);
      const mapped = data.map(item => ({
        id: String(item.id),
        title: String(item.title || ''),
        weakness_count: (item.weakness_count as RedTeamReport['weakness_count']) || { critical: 0, high: 0, medium: 0, low: 0 },
        summary: String(item.summary || ''),
        created_at: String(item.created_at || ''),
      }));
      setReports(mapped);
    } catch (err) {
      toast.error(`Failed to load reports: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  if (loading) return <LoadingSkeleton />;

  if (reports.length === 0) {
    return <EmptyState icon="ShieldAlert" label="No reports yet" description="Red-team your case strategy to identify critical weaknesses and vulnerabilities." />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {reports.map((report) => (
        <div
          key={report.id}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '16px 20px', borderRadius: '12px',
            border: '1px solid #e5e7eb', background: 'white',
          }}
        >
          <div style={{ flex: 1 }}>
            <h3 style={{ margin: '0 0 4px 0', fontSize: '15px', fontWeight: 600 }}>{report.title}</h3>
            <p style={{ margin: 0, fontSize: '13px', color: '#6b7280' }}>{report.summary}</p>
          </div>
          <div style={{ display: 'flex', gap: '8px', marginLeft: '24px' }}>
            <WeaknessBadge severity="critical" count={report.weakness_count.critical} />
            <WeaknessBadge severity="high" count={report.weakness_count.high} />
            <WeaknessBadge severity="medium" count={report.weakness_count.medium} />
            <WeaknessBadge severity="low" count={report.weakness_count.low} />
          </div>
          <div style={{ marginLeft: '24px', color: '#9ca3af' }}>
            <Icon name="ChevronRight" size={20} />
          </div>
        </div>
      ))}
    </div>
  );
}

function WeaknessBadge({ severity, count }: { severity: string, count: number }) {
  if (count === 0) return null;
  const color = getSeverityColor(severity);
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '4px',
      padding: '2px 8px', borderRadius: '12px',
      background: `${color}12`, color: color,
      fontSize: '11px', fontWeight: 700,
    }}>
      <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: color }} />
      {count} {severity.charAt(0).toUpperCase() + severity.slice(1)}
    </div>
  );
}

// ============================================
// Tactical Tab
// ============================================

function TacticalTab() {
  const { toast } = useToast();
  const [models, setModels] = useState<TacticalModel[]>([]);
  const [loading, setLoading] = useState(true);

  const loadModels = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams(window.location.search);
      const projectId = params.get('project_id') || params.get('projectId') || 'default';
      const data = await api.listTacticalModels(projectId);
      const mapped = data.map(item => ({
        id: String(item.id),
        title: String(item.title || ''),
        predicted_moves: (item.predicted_moves as TacticalModel['predicted_moves']) || [],
        created_at: String(item.created_at || ''),
      }));
      setModels(mapped);
    } catch (err) {
      toast.error(`Failed to load tactical models: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  if (loading) return <LoadingSkeleton />;

  if (models.length === 0) {
    return <EmptyState icon="Network" label="No models yet" description="Map predicted respondent procedural moves and timeline strategies." />;
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))', gap: '20px' }}>
      {models.map((model) => (
        <div key={model.id} style={{ padding: '20px', borderRadius: '12px', border: '1px solid #e5e7eb', background: 'white' }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 600 }}>{model.title}</h3>
          <div style={{ position: 'relative', paddingLeft: '20px' }}>
            <div style={{ position: 'absolute', left: '4px', top: '0', bottom: '0', width: '2px', background: '#e5e7eb' }} />
            {model.predicted_moves.map((move, i) => (
              <div key={i} style={{ marginBottom: '16px', position: 'relative' }}>
                <div style={{
                  position: 'absolute', left: '-20px', top: '4px',
                  width: '10px', height: '10px', borderRadius: '50%',
                  background: '#2563eb', border: '2px solid white',
                }} />
                <div style={{ fontSize: '11px', color: '#6b7280', fontWeight: 600, textTransform: 'uppercase' }}>{move.timing}</div>
                <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px' }}>{move.move}</div>
                <div style={{ fontSize: '12px', color: '#4b5563', marginTop: '2px' }}>Impact: {move.impact}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================
// Detail View
// ============================================

function StrategistDetailView({ itemId }: { itemId: string }) {
  const { toast } = useToast();
  const [item, setItem] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const data = await api.getItem(itemId);
        setItem(data);
      } catch (err) {
        toast.error(`Failed to load detail: ${String(err)}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [itemId, toast]);

  if (loading) return <LoadingSkeleton />;
  if (!item) return <div style={{ padding: '24px' }}>Item not found</div>;

  const predictedArgs = (item.metadata?.predicted_arguments as Prediction['predicted_arguments']) || [];

  return (
    <div style={{ padding: '24px', maxWidth: '1000px' }}>
      <button
        onClick={() => window.history.back()}
        style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          background: 'none', border: 'none', color: '#6b7280',
          cursor: 'pointer', fontSize: '13px', marginBottom: '16px',
        }}
      >
        <Icon name="ArrowLeft" size={14} /> Back to Strategist
      </button>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, margin: 0 }}>{String(item.title)}</h1>
          <p style={{ color: '#6b7280', marginTop: '4px' }}>{String(item.description)}</p>
        </div>
        <div style={{ padding: '4px 12px', borderRadius: '12px', background: '#f3f4f6', fontSize: '12px', fontWeight: 600 }}>
          {formatDate(String(item.created_at))}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '20px' }}>
        <section style={{ padding: '24px', borderRadius: '12px', border: '1px solid #e5e7eb', background: 'white' }}>
          <h2 style={{ fontSize: '18px', fontWeight: 600, margin: '0 0 20px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Icon name="Zap" size={18} /> Predicted Adversarial Arguments
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {predictedArgs.map((arg, i) => (
              <div key={i} style={{ padding: '20px', borderRadius: '8px', border: '1px solid #f3f4f6', background: '#f9fafb' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <span style={{
                    padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 700,
                    background: `${getSeverityColor(arg.severity)}12`, color: getSeverityColor(arg.severity),
                  }}>
                    {String(arg.severity).toUpperCase()} PRIORITY
                  </span>
                  <span style={{ fontSize: '12px', color: '#9ca3af' }}>Probability: {Math.round(arg.probability * 100)}%</span>
                </div>
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', marginBottom: '4px' }}>Respondent Argument</div>
                  <div style={{ fontSize: '15px', fontWeight: 600, color: '#111827' }}>{arg.argument}</div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', marginBottom: '4px' }}>Recommended Counter</div>
                  <div style={{ fontSize: '14px', lineHeight: 1.6, color: '#374151' }}>{arg.counter_argument}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {!!item.metadata?.weaknesses && (
          <section style={{ padding: '24px', borderRadius: '12px', border: '1px solid #e5e7eb', background: 'white' }}>
            <h2 style={{ fontSize: '18px', fontWeight: 600, margin: '0 0 20px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Icon name="ShieldAlert" size={18} /> Vulnerability Assessment
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {(item.metadata.weaknesses as any[]).map((w, i) => (
                <div key={i} style={{ display: 'flex', gap: '12px', padding: '12px', borderRadius: '8px', background: '#fff5f5', border: '1px solid #fed7d7' }}>
                  <Icon name="AlertTriangle" size={18} color="#e53e3e" />
                  <div>
                    <div style={{ fontWeight: 600, color: '#c53030', fontSize: '14px' }}>{w.title}</div>
                    <div style={{ fontSize: '13px', color: '#7b2d26', marginTop: '2px' }}>{w.mitigation}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

// ============================================
// Dialogs
// ============================================

function GeneratePredictionDialog({ onClose }: { onClose: () => void }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [claim, setClaim] = useState('');
  const [context, setContext] = useState('');

  const handleGenerate = async () => {
    if (!claim.trim()) {
      toast.error('Please enter a claim description');
      return;
    }

    try {
      setLoading(true);
      const params = new URLSearchParams(window.location.search);
      const projectId = params.get('project_id') || params.get('projectId') || '';

      await api.createPrediction({
        project_id: projectId,
        claim_id: claim, // In real impl, this might be a text input
        metadata: {
          context: context,
          manual_entry: true,
        }
      });

      toast.success('Prediction task queued successfully');
      onClose();
    } catch (err) {
      toast.error(`Failed to trigger prediction: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center',
      justifyContent: 'center', zIndex: 1000, padding: '20px',
    }}>
      <div style={{
        background: 'white', borderRadius: '12px', width: '100%',
        maxWidth: '500px', padding: '24px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)',
      }}>
        <h2 style={{ margin: '0 0 20px 0', fontSize: '20px', fontWeight: 600 }}>Generate Prediction</h2>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '6px' }}>Claim / Submission Text</label>
          <textarea
            value={claim}
            onChange={(e) => setClaim(e.target.value)}
            placeholder="Describe the claim or legal argument to test..."
            style={{
              width: '100%', height: '100px', padding: '12px',
              borderRadius: '8px', border: '1px solid #e5e7eb',
              fontSize: '14px', resize: 'none',
            }}
          />
        </div>

        <div style={{ marginBottom: '24px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '6px' }}>Respondent Context (Optional)</label>
          <textarea
            value={context}
            onChange={(e) => setContext(e.target.value)}
            placeholder="e.g. respondent history, specific legal precedents, known defense style..."
            style={{
              width: '100%', height: '80px', padding: '12px',
              borderRadius: '8px', border: '1px solid #e5e7eb',
              fontSize: '14px', resize: 'none',
            }}
          />
        </div>

        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #e5e7eb', background: 'white', cursor: 'pointer' }}
          >
            Cancel
          </button>
          <button
            onClick={handleGenerate}
            disabled={loading}
            style={{
              padding: '8px 24px', borderRadius: '6px', border: 'none',
              background: '#2563eb', color: 'white', fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? 'Processing...' : 'Generate Model'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Helpers
// ============================================

function EmptyState({ icon, label, description }: { icon: string; label: string; description: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '60px 24px', background: '#f9fafb', borderRadius: '12px', border: '2px dashed #e5e7eb' }}>
      <Icon name={icon} size={48} color="#9ca3af" />
      <h3 style={{ margin: '16px 0 8px 0', fontSize: '16px', fontWeight: 600, color: '#374151' }}>{label}</h3>
      <p style={{ margin: 0, fontSize: '14px', color: '#6b7280', maxWidth: '400px', marginLeft: 'auto', marginRight: 'auto' }}>{description}</p>
    </div>
  );
}

function getSeverityColor(severity: string): string {
  switch (String(severity).toLowerCase()) {
    case 'critical': return '#dc2626'; // Red
    case 'high': return '#ea580c';     // Orange
    case 'medium': return '#d97706';   // Amber
    case 'low': return '#16a34a';      // Green
    default: return '#6b7280';
  }
}

function formatDate(d: string): string {
  if (!d) return 'n/a';
  try {
    return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return d;
  }
}
