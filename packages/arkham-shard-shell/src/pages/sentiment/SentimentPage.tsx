/**
 * SentimentPage - Document Sentiment & Tone Analyzer
 *
 * LLM-powered analysis of tone, sentiment, and language patterns in workplace
 * communications. Detects hostility escalation, gaslighting patterns,
 * passive-aggressive language, and tone shifts correlating with discriminatory intent.
 * Compares language toward claimant vs. comparators.
 */

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';

import * as api from './api';
import type {
  SentimentAnalysis,
  SentimentPattern,
  ComparatorDiff,
} from './types';
import {
  TONE_CATEGORY_OPTIONS,
  PATTERN_TYPE_OPTIONS,
  SENTIMENT_DIRECTION_OPTIONS,
} from './types';

type TabKey = 'analyses' | 'patterns' | 'comparators';

export function SentimentPage() {
  const [searchParams] = useSearchParams();
  const analysisId = searchParams.get('analysisId') || searchParams.get('itemId');

  if (analysisId) {
    return <AnalysisDetailView analysisId={analysisId} />;
  }

  return <SentimentListView />;
}

// ============================================
// List View — Tabbed: Analyses / Patterns / Comparators
// ============================================

function SentimentListView() {
  const [activeTab, setActiveTab] = useState<TabKey>('analyses');

  const tabs: { key: TabKey; label: string; icon: string }[] = [
    { key: 'analyses', label: 'Analyses', icon: 'HeartPulse' },
    { key: 'patterns', label: 'Patterns', icon: 'TrendingUp' },
    { key: 'comparators', label: 'Comparator Divergence', icon: 'GitCompare' },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: '1200px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <Icon name="HeartPulse" size={24} /> Sentiment & Tone
          </h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', marginTop: '4px', fontSize: '14px' }}>
            Detect hostility escalation, gaslighting, and discriminatory language patterns
          </p>
        </div>
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
      {activeTab === 'analyses' && <AnalysesTab />}
      {activeTab === 'patterns' && <PatternsTab />}
      {activeTab === 'comparators' && <ComparatorsTab />}
    </div>
  );
}

// ============================================
// Analyses Tab — list from /items endpoint
// ============================================

function AnalysesTab() {
  const { toast } = useToast();
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);

  const loadItems = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listItems();
      setItems(data.items as unknown as Array<Record<string, unknown>>);
    } catch (err) {
      toast.error(`Failed to load analyses: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  if (loading) return <LoadingSkeleton />;

  if (items.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        <Icon name="HeartPulse" size={48} />
        <p style={{ marginTop: '12px', fontWeight: 500 }}>No sentiment analyses yet</p>
        <p style={{ fontSize: '13px' }}>
          Trigger analysis on documents or communication threads to detect
          <br />tone shifts, hostility patterns, and discriminatory language.
        </p>

        {/* Tone legend */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '20px', flexWrap: 'wrap' }}>
          {TONE_CATEGORY_OPTIONS.map(t => (
            <span key={t.value} style={{
              padding: '3px 10px', borderRadius: '12px', fontSize: '11px', fontWeight: 600,
              background: `${t.color}12`, color: t.color,
            }}>
              {t.label}
            </span>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {items.map((item) => {
        const sentiment = typeof item.overall_sentiment === 'number'
          ? item.overall_sentiment
          : typeof item.metadata === 'object' && item.metadata
            ? (item.metadata as Record<string, unknown>).overall_sentiment as number | undefined
            : undefined;

        const sentimentDir = getSentimentDirection(sentiment);
        const sentimentConf = SENTIMENT_DIRECTION_OPTIONS.find(s => s.value === sentimentDir);
        const toneScores = (item.tone_scores || []) as Array<Record<string, unknown>>;

        return (
          <div
            key={String(item.id)}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '14px 16px', borderRadius: '8px',
              border: '1px solid var(--arkham-border, #e5e7eb)',
              borderLeft: `4px solid ${sentimentConf?.color || '#6b7280'}`,
              background: 'var(--arkham-bg-secondary, white)',
              cursor: 'pointer',
            }}
          >
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontWeight: 600 }}>
                  {String(item.title || item.summary || `Analysis ${String(item.id).slice(0, 8)}`)}
                </span>
                {!!item.document_id && (
                  <span style={{
                    padding: '1px 6px', borderRadius: '4px', fontSize: '11px',
                    background: 'var(--arkham-bg-tertiary, #f3f4f6)',
                    color: 'var(--arkham-text-muted, #9ca3af)', fontFamily: 'monospace',
                  }}>
                    doc:{String(item.document_id).slice(0, 8)}
                  </span>
                )}
              </div>
              <div style={{ fontSize: '13px', color: 'var(--arkham-text-muted, #6b7280)', marginTop: '3px' }}>
                {String(item.description || item.summary || 'Pending analysis...')}
              </div>

              {/* Inline tone bars */}
              {toneScores.length > 0 && (
                <div style={{ display: 'flex', gap: '4px', marginTop: '8px', flexWrap: 'wrap' }}>
                  {toneScores.slice(0, 4).map((ts, i) => {
                    const toneConf = TONE_CATEGORY_OPTIONS.find(t => t.value === ts.category);
                    const score = typeof ts.score === 'number' ? ts.score : 0;
                    return (
                      <ToneMiniBar
                        key={i}
                        label={toneConf?.label || String(ts.category)}
                        score={score}
                        color={toneConf?.color || '#6b7280'}
                      />
                    );
                  })}
                </div>
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              {/* Sentiment gauge */}
              {sentiment != null && (
                <SentimentGauge value={sentiment} size={40} />
              )}

              {sentimentConf && (
                <span style={{
                  padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 700,
                  background: `${sentimentConf.color}12`, color: sentimentConf.color,
                }}>
                  {sentimentConf.label}
                </span>
              )}

              <span style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)' }}>
                {formatDate(String(item.created_at || ''))}
              </span>

              <Icon name="ChevronRight" size={16} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ============================================
// Patterns Tab
// ============================================

function PatternsTab() {
  const { toast } = useToast();
  const [patterns, setPatterns] = useState<SentimentPattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [projectId, setProjectId] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // Try to get project from URL or use default
        const params = new URLSearchParams(window.location.search);
        const pid = params.get('project_id') || params.get('projectId');
        if (pid) {
          setProjectId(pid);
          const data = await api.listPatterns(pid);
          setPatterns(data);
        }
      } catch (err) {
        toast.error(`Failed to load patterns: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [toast]);

  if (loading) return <LoadingSkeleton />;

  if (!projectId) {
    return (
      <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        <Icon name="TrendingUp" size={48} />
        <p style={{ marginTop: '12px', fontWeight: 500 }}>Select a project to view patterns</p>
        <p style={{ fontSize: '13px' }}>
          Patterns are detected across analyses within a project scope.
          <br />Use the project selector in the top bar to choose a project.
        </p>

        {/* Pattern type legend */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '20px', flexWrap: 'wrap' }}>
          {PATTERN_TYPE_OPTIONS.map(p => (
            <span key={p.value} style={{
              padding: '3px 10px', borderRadius: '12px', fontSize: '11px', fontWeight: 600,
              background: `${p.color}12`, color: p.color,
            }}>
              {p.label}
            </span>
          ))}
        </div>
      </div>
    );
  }

  if (patterns.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        <Icon name="TrendingUp" size={48} />
        <p style={{ marginTop: '12px', fontWeight: 500 }}>No patterns detected yet</p>
        <p style={{ fontSize: '13px' }}>
          Run sentiment analyses on multiple documents or threads to identify
          <br />hostility escalation, gaslighting, and tone shift patterns.
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {patterns.map((pattern) => {
        const pConf = PATTERN_TYPE_OPTIONS.find(p => p.value === pattern.type);
        const sigPct = Math.round(pattern.significance_score * 100);

        return (
          <div
            key={pattern.id}
            style={{
              padding: '14px 16px', borderRadius: '8px',
              border: '1px solid var(--arkham-border, #e5e7eb)',
              borderLeft: `4px solid ${pConf?.color || '#6b7280'}`,
              background: 'var(--arkham-bg-secondary, white)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Icon name="TrendingUp" size={14} />
                  {pConf && (
                    <span style={{
                      padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 700,
                      background: `${pConf.color}12`, color: pConf.color,
                    }}>
                      {pConf.label}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: '14px', marginTop: '6px', lineHeight: 1.6 }}>
                  {pattern.description}
                </div>
                {pattern.analysis_ids.length > 0 && (
                  <div style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)', marginTop: '6px' }}>
                    Across {pattern.analysis_ids.length} analyses
                  </div>
                )}
              </div>
              <div style={{ textAlign: 'right', minWidth: '80px' }}>
                <div style={{ fontSize: '11px', color: 'var(--arkham-text-muted, #9ca3af)', textTransform: 'uppercase', fontWeight: 600 }}>
                  Significance
                </div>
                <div style={{ fontSize: '22px', fontWeight: 700, color: getSignificanceColor(sigPct) }}>
                  {sigPct}%
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ============================================
// Comparators Tab
// ============================================

function ComparatorsTab() {
  const { toast } = useToast();
  const [diffs, setDiffs] = useState<ComparatorDiff[]>([]);
  const [loading, setLoading] = useState(true);
  const [projectId, setProjectId] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const params = new URLSearchParams(window.location.search);
        const pid = params.get('project_id') || params.get('projectId');
        if (pid) {
          setProjectId(pid);
          const data = await api.listComparatorDiffs(pid);
          setDiffs(data);
        }
      } catch (err) {
        toast.error(`Failed to load comparator diffs: ${err}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [toast]);

  if (loading) return <LoadingSkeleton />;

  if (!projectId || diffs.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '48px', color: 'var(--arkham-text-muted, #6b7280)' }}>
        <Icon name="GitCompare" size={48} />
        <p style={{ marginTop: '12px', fontWeight: 500 }}>
          {!projectId ? 'Select a project to view comparator divergence' : 'No comparator divergence found'}
        </p>
        <p style={{ fontSize: '13px' }}>
          Compare tone and language used toward the claimant vs. comparators.
          <br />Divergent treatment in language supports s.13 and s.26 arguments.
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {diffs.map((diff) => {
        const divPct = Math.round(diff.divergence_score * 100);
        const divColor = getDivergenceColor(divPct);

        return (
          <div
            key={diff.id}
            style={{
              padding: '16px', borderRadius: '8px',
              border: '1px solid var(--arkham-border, #e5e7eb)',
              borderLeft: `4px solid ${divColor}`,
              background: 'var(--arkham-bg-secondary, white)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <Icon name="GitCompare" size={14} />
                  <span style={{ fontWeight: 600 }}>Divergence Analysis</span>
                </div>
                <p style={{ fontSize: '14px', margin: '0 0 8px 0', lineHeight: 1.6 }}>
                  {diff.description}
                </p>

                {/* Findings */}
                {diff.findings.length > 0 && (
                  <div style={{
                    padding: '10px 14px', borderRadius: '6px',
                    background: 'var(--arkham-bg-tertiary, #f9fafb)',
                    borderLeft: `2px solid ${divColor}`,
                  }}>
                    <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--arkham-text-muted, #9ca3af)', marginBottom: '4px' }}>
                      Findings
                    </div>
                    <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '13px', lineHeight: 1.7 }}>
                      {diff.findings.map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Analysis refs */}
                <div style={{ display: 'flex', gap: '8px', marginTop: '8px', fontSize: '12px', color: 'var(--arkham-text-muted, #9ca3af)' }}>
                  <span style={{ fontFamily: 'monospace' }}>
                    Claimant: {diff.claimant_analysis_id.slice(0, 8)}
                  </span>
                  <span>vs.</span>
                  <span style={{ fontFamily: 'monospace' }}>
                    Comparator: {diff.comparator_analysis_id.slice(0, 8)}
                  </span>
                </div>
              </div>

              <div style={{ textAlign: 'right', minWidth: '100px' }}>
                <div style={{ fontSize: '11px', color: 'var(--arkham-text-muted, #9ca3af)', textTransform: 'uppercase', fontWeight: 600 }}>
                  Divergence
                </div>
                <div style={{ fontSize: '28px', fontWeight: 700, color: divColor }}>
                  {divPct}%
                </div>
                <DivergenceBar value={divPct} color={divColor} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ============================================
// Analysis Detail View
// ============================================

function AnalysisDetailView({ analysisId }: { analysisId: string }) {
  const { toast } = useToast();
  const [analysis, setAnalysis] = useState<SentimentAnalysis | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const data = await api.getAnalysis(analysisId);
        setAnalysis(data);
      } catch {
        // Fallback: try generic item endpoint
        try {
          const data = await api.getItem(analysisId);
          setAnalysis(data as unknown as SentimentAnalysis);
        } catch (err) {
          toast.error(`Failed to load analysis: ${err}`);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [analysisId, toast]);

  if (loading) return <LoadingSkeleton />;
  if (!analysis) return <div style={{ padding: '24px' }}>Analysis not found</div>;

  const toneScores = analysis.tone_scores || [];
  const sentiment = analysis.overall_sentiment;
  const sentimentDir = getSentimentDirection(sentiment);
  const sentimentConf = SENTIMENT_DIRECTION_OPTIONS.find(s => s.value === sentimentDir);

  return (
    <div style={{ padding: '24px', maxWidth: '1000px' }}>
      {/* Breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <a href="/sentiment" style={{ color: 'var(--arkham-text-muted, #6b7280)', textDecoration: 'none', fontSize: '13px' }}>
          Sentiment
        </a>
        <Icon name="ChevronRight" size={12} />
      </div>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <Icon name="HeartPulse" size={22} />
            Analysis {analysisId.slice(0, 8)}
          </h1>
          <p style={{ color: 'var(--arkham-text-muted, #6b7280)', marginTop: '4px', fontSize: '14px' }}>
            {analysis.summary || 'Pending analysis...'}
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <SentimentGauge value={sentiment} size={56} />
          {sentimentConf && (
            <span style={{
              padding: '4px 12px', borderRadius: '12px', fontSize: '13px', fontWeight: 700,
              background: `${sentimentConf.color}12`, color: sentimentConf.color,
            }}>
              {sentimentConf.label}
            </span>
          )}
        </div>
      </div>

      {/* Overall score bar */}
      <div style={{
        padding: '16px 20px', borderRadius: '8px', marginBottom: '20px',
        background: 'var(--arkham-bg-secondary, white)',
        border: '1px solid var(--arkham-border, #e5e7eb)',
      }}>
        <div style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--arkham-text-muted, #9ca3af)', marginBottom: '8px' }}>
          Overall Sentiment Score
        </div>
        <SentimentScale value={sentiment} />
      </div>

      {/* Tone Breakdown */}
      <div style={{
        padding: '20px', borderRadius: '8px', marginBottom: '20px',
        background: 'var(--arkham-bg-secondary, white)',
        border: '1px solid var(--arkham-border, #e5e7eb)',
      }}>
        <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Icon name="BarChart3" size={18} /> Tone Breakdown
        </h3>

        {toneScores.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '24px', color: 'var(--arkham-text-muted, #6b7280)', fontSize: '14px' }}>
            No tone scores available. Run analysis to generate tone breakdown.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {toneScores.map((ts) => {
              const toneConf = TONE_CATEGORY_OPTIONS.find(t => t.value === ts.category);
              const score = typeof ts.score === 'number' ? ts.score : 0;
              const pct = Math.round(score * 100);

              return (
                <div key={ts.id}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{
                        width: '8px', height: '8px', borderRadius: '50%',
                        background: toneConf?.color || '#6b7280', display: 'inline-block',
                      }} />
                      {toneConf?.label || ts.category}
                    </span>
                    <span style={{ fontSize: '13px', fontWeight: 700, color: toneConf?.color || '#6b7280' }}>
                      {pct}%
                    </span>
                  </div>
                  <div style={{
                    height: '8px', borderRadius: '4px',
                    background: 'var(--arkham-bg-tertiary, #f3f4f6)',
                    overflow: 'hidden',
                  }}>
                    <div style={{
                      height: '100%', width: `${pct}%`, borderRadius: '4px',
                      background: toneConf?.color || '#6b7280',
                      transition: 'width 0.3s ease',
                    }} />
                  </div>
                  {ts.reasoning && (
                    <div style={{ fontSize: '12px', color: 'var(--arkham-text-muted, #6b7280)', marginTop: '4px', paddingLeft: '14px' }}>
                      {ts.reasoning}
                    </div>
                  )}
                  {ts.evidence_segments && ts.evidence_segments.length > 0 && (
                    <div style={{ marginTop: '6px', paddingLeft: '14px' }}>
                      {ts.evidence_segments.map((seg, i) => (
                        <div key={i} style={{
                          fontSize: '12px', padding: '6px 10px', marginTop: '4px',
                          background: `${toneConf?.color || '#6b7280'}08`,
                          borderLeft: `2px solid ${toneConf?.color || '#6b7280'}`,
                          borderRadius: '4px', fontStyle: 'italic',
                          color: 'var(--arkham-text-muted, #4b5563)',
                        }}>
                          &ldquo;{seg}&rdquo;
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Meta */}
      <div style={{
        padding: '16px 20px', borderRadius: '8px',
        background: 'var(--arkham-bg-tertiary, #f9fafb)',
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '12px',
        fontSize: '13px',
      }}>
        {analysis.document_id && (
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--arkham-text-muted, #9ca3af)' }}>
              Document
            </div>
            <div style={{ fontFamily: 'monospace', marginTop: '2px' }}>{analysis.document_id.slice(0, 12)}...</div>
          </div>
        )}
        {analysis.thread_id && (
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--arkham-text-muted, #9ca3af)' }}>
              Thread
            </div>
            <div style={{ fontFamily: 'monospace', marginTop: '2px' }}>{analysis.thread_id.slice(0, 12)}...</div>
          </div>
        )}
        <div>
          <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--arkham-text-muted, #9ca3af)' }}>
            Created
          </div>
          <div style={{ marginTop: '2px' }}>{formatDate(String(analysis.created_at))}</div>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Shared Components
// ============================================

/** Mini tone bar for list items */
function ToneMiniBar({ label, score, color }: { label: string; score: number; color: string }) {
  const pct = Math.round(score * 100);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
      <span style={{ fontSize: '10px', color: 'var(--arkham-text-muted, #9ca3af)', minWidth: '60px' }}>{label}</span>
      <div style={{ width: '40px', height: '4px', borderRadius: '2px', background: 'var(--arkham-bg-tertiary, #e5e7eb)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: '2px' }} />
      </div>
      <span style={{ fontSize: '10px', fontWeight: 600, color, minWidth: '24px' }}>{pct}%</span>
    </div>
  );
}

/** Circular sentiment gauge */
function SentimentGauge({ value, size }: { value: number; size: number }) {
  // value: -1 (hostile) to +1 (supportive)
  const color = getSentimentColor(value);
  const displayVal = value >= 0 ? `+${value.toFixed(1)}` : value.toFixed(1);

  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      border: `3px solid ${color}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: size * 0.3, fontWeight: 700, color,
      background: `${color}08`,
    }}>
      {displayVal}
    </div>
  );
}

/** Horizontal sentiment scale bar */
function SentimentScale({ value }: { value: number }) {
  // value: -1 to +1, map to 0-100%
  const pct = ((value + 1) / 2) * 100;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--arkham-text-muted, #9ca3af)', marginBottom: '4px' }}>
        <span>Hostile</span>
        <span>Neutral</span>
        <span>Supportive</span>
      </div>
      <div style={{
        height: '12px', borderRadius: '6px', position: 'relative',
        background: 'linear-gradient(to right, #dc2626, #ea580c, #d97706, #6b7280, #2563eb, #059669, #16a34a)',
        overflow: 'visible',
      }}>
        <div style={{
          position: 'absolute', top: '-2px',
          left: `${pct}%`, transform: 'translateX(-50%)',
          width: '16px', height: '16px', borderRadius: '50%',
          background: 'white', border: '3px solid #1f2937',
          boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
        }} />
      </div>
    </div>
  );
}

/** Divergence progress bar */
function DivergenceBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{
      width: '80px', height: '6px', borderRadius: '3px',
      background: 'var(--arkham-bg-tertiary, #e5e7eb)', marginTop: '6px',
      overflow: 'hidden',
    }}>
      <div style={{ height: '100%', width: `${value}%`, background: color, borderRadius: '3px' }} />
    </div>
  );
}

// ============================================
// Helpers
// ============================================

function getSentimentDirection(val: number | undefined): string {
  if (val == null) return 'neutral';
  if (val <= -0.6) return 'hostile';
  if (val <= -0.2) return 'negative';
  if (val <= 0.2) return 'neutral';
  if (val <= 0.6) return 'positive';
  return 'supportive';
}

function getSentimentColor(val: number): string {
  if (val <= -0.6) return '#dc2626';
  if (val <= -0.2) return '#ea580c';
  if (val <= 0.2) return '#6b7280';
  if (val <= 0.6) return '#2563eb';
  return '#16a34a';
}

function getSignificanceColor(pct: number): string {
  if (pct >= 80) return '#dc2626';
  if (pct >= 60) return '#ea580c';
  if (pct >= 40) return '#d97706';
  return '#6b7280';
}

function getDivergenceColor(pct: number): string {
  if (pct >= 70) return '#dc2626';
  if (pct >= 50) return '#ea580c';
  if (pct >= 30) return '#d97706';
  return '#2563eb';
}

function formatDate(d: string): string {
  try {
    return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return d;
  }
}
