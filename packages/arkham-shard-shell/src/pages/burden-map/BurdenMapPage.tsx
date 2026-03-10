/**
 * BurdenMapPage - Burden of Proof Mapper
 *
 * A domain-specific implementation for mapping the burden of proof in legal claims.
 * Tracks elements of a claim, assigns burden (claimant/respondent), weighs evidence,
 * and visualizes the status using a traffic-light system.
 * Includes support for burden-shifting tracking (e.g. s.136 Equality Act 2010).
 */

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';

type TrafficStatus = 'green' | 'amber' | 'red';

interface DashboardStats {
  green: number;
  amber: number;
  red: number;
  total: number;
}

interface BurdenElement {
  id: string;
  title: string;
  description: string;
  claim_type: string;
  statutory_reference: string;
  burden_holder: 'claimant' | 'respondent';
  status: TrafficStatus;
  current_weight: number;
  required_weight: number;
  has_shifted: boolean;
  evidence_count: number;
}

const STATUS_COLORS: Record<TrafficStatus, string> = {
  green: '#10b981',
  amber: '#f59e0b',
  red: '#ef4444',
};

const STATUS_LABELS: Record<TrafficStatus, string> = {
  green: 'Burden Met',
  amber: 'Borderline',
  red: 'Evidentiary Gap',
};

export function BurdenMapPage() {
  const { toast } = useToast();
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get('projectId') || undefined;

  const [elements, setElements] = useState<BurdenElement[]>([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<DashboardStats>({ green: 0, amber: 0, red: 0, total: 0 });

  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showWeightDialog, setShowWeightDialog] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getBurdenDashboard(projectId);

      const mapped: BurdenElement[] = (data.elements || []).map((e: Record<string, unknown>) => ({
        id: String(e.element_id || e.id || ''),
        title: String(e.title || 'Untitled Element'),
        description: String(e.description || ''),
        claim_type: String(e.claim_type || 'General'),
        statutory_reference: String(e.statutory_reference || ''),
        burden_holder: (e.burden_holder === 'respondent' ? 'respondent' : 'claimant') as
          | 'claimant'
          | 'respondent',
        status: (e.status as TrafficStatus) || 'red',
        current_weight: Number(e.current_weight || 0),
        required_weight: Number(e.required_weight || 100),
        has_shifted: !!e.has_shifted,
        evidence_count: Number(e.evidence_count || 0),
      }));

      setElements(mapped);

      const newStats = mapped.reduce(
        (acc, el) => {
          acc[el.status]++;
          acc.total++;
          return acc;
        },
        { green: 0, amber: 0, red: 0, total: 0 }
      );

      setStats(newStats);
    } catch (err) {
      toast.error(`Failed to load burden map: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  if (loading) return <LoadingSkeleton />;

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: '32px',
        }}
      >
        <div>
          <h1
            style={{
              fontSize: '28px',
              fontWeight: 700,
              margin: 0,
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <Icon name="Scale" size={32} color="#3b82f6" />
            Burden of Proof Mapper
          </h1>
          <p style={{ color: '#6b7280', marginTop: '8px', fontSize: '15px' }}>
            Map statutory elements, track evidentiary weights, and visualize the status of your
            claim.
          </p>
        </div>

        <button
          onClick={() => setShowCreateDialog(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '10px 20px',
            background: '#3b82f6',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            fontWeight: 600,
            cursor: 'pointer',
            boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
          }}
        >
          <Icon name="Plus" size={18} />
          Create Element
        </button>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '20px',
          marginBottom: '32px',
        }}
      >
        <SummaryCard label="Total Elements" value={stats.total} icon="ListChecks" color="#3b82f6" />
        <SummaryCard
          label="Burden Met"
          value={stats.green}
          icon="CheckCircle"
          color={STATUS_COLORS.green}
        />
        <SummaryCard
          label="Borderline"
          value={stats.amber}
          icon="AlertCircle"
          color={STATUS_COLORS.amber}
        />
        <SummaryCard
          label="Gaps Identified"
          value={stats.red}
          icon="XCircle"
          color={STATUS_COLORS.red}
        />
      </div>

      <div
        style={{
          background: '#eff6ff',
          border: '1px solid #bfdbfe',
          borderRadius: '12px',
          padding: '16px 20px',
          marginBottom: '32px',
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
        }}
      >
        <div
          style={{
            background: '#3b82f6',
            color: 'white',
            padding: '8px',
            borderRadius: '8px',
            display: 'flex',
          }}
        >
          <Icon name="Info" size={20} />
        </div>
        <div style={{ flex: 1 }}>
          <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#1e40af' }}>
            Section 136 Equality Act 2010 Tracking
          </h4>
          <p style={{ margin: '4px 0 0 0', fontSize: '14px', color: '#1e40af', opacity: 0.8 }}>
            System is tracking the shift of burden from Claimant to Respondent once prima facie case
            is established.
          </p>
        </div>
        <div
          style={{
            fontSize: '12px',
            fontWeight: 700,
            background: '#dbeafe',
            color: '#1e40af',
            padding: '4px 10px',
            borderRadius: '20px',
            textTransform: 'uppercase',
          }}
        >
          Active
        </div>
      </div>

      {elements.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: '64px',
            background: 'white',
            borderRadius: '16px',
            border: '1px dashed #d1d5db',
          }}
        >
          <Icon name="Search" size={48} color="#9ca3af" />
          <h3 style={{ marginTop: '16px', color: '#374151' }}>No elements found</h3>
          <p style={{ color: '#6b7280' }}>Start by creating the first element of your claim.</p>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))',
            gap: '24px',
          }}
        >
          {elements.map((element) => (
            <ElementCard
              key={element.id}
              element={element}
              onAddWeight={() => setShowWeightDialog(element.id)}
            />
          ))}
        </div>
      )}

      {/* Dialogs */}
      {!!showCreateDialog && (
        <CreateElementDialog
          projectId={projectId}
          onClose={() => setShowCreateDialog(false)}
          onSuccess={() => {
            setShowCreateDialog(false);
            loadDashboard();
          }}
        />
      )}

      {!!showWeightDialog && (
        <AddWeightDialog
          elementId={showWeightDialog}
          onClose={() => setShowWeightDialog(null)}
          onSuccess={() => {
            setShowWeightDialog(null);
            loadDashboard();
          }}
        />
      )}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: number;
  icon: string;
  color: string;
}) {
  return (
    <div
      style={{
        background: 'white',
        padding: '20px',
        borderRadius: '12px',
        border: '1px solid #e5e7eb',
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
      }}
    >
      <div
        style={{
          background: `${color}15`,
          color: color,
          padding: '12px',
          borderRadius: '10px',
          display: 'flex',
        }}
      >
        <Icon name={icon} size={24} />
      </div>
      <div>
        <div style={{ fontSize: '13px', color: '#6b7280', fontWeight: 500 }}>{label}</div>
        <div style={{ fontSize: '24px', fontWeight: 700, color: '#111827' }}>{value}</div>
      </div>
    </div>
  );
}

function ElementCard({
  element,
  onAddWeight,
}: {
  element: BurdenElement;
  onAddWeight: () => void;
}) {
  const percentage = Math.min(
    100,
    Math.round((element.current_weight / element.required_weight) * 100)
  );
  const statusColor = STATUS_COLORS[element.status];

  return (
    <div
      style={{
        background: 'white',
        borderRadius: '16px',
        border: '1px solid #e5e7eb',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        transition: 'transform 0.2s, box-shadow 0.2s',
        position: 'relative',
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          bottom: 0,
          width: '6px',
          background: statusColor,
        }}
      />

      <div style={{ padding: '20px 20px 20px 26px' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            marginBottom: '12px',
          }}
        >
          <div>
            <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: '#111827' }}>
              {element.title}
            </h3>
            {!!element.statutory_reference && (
              <div
                style={{
                  fontSize: '12px',
                  color: '#6b7280',
                  marginTop: '2px',
                  fontFamily: 'monospace',
                }}
              >
                {element.statutory_reference}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 700,
                padding: '4px 8px',
                borderRadius: '6px',
                background: element.burden_holder === 'claimant' ? '#eff6ff' : '#fff7ed',
                color: element.burden_holder === 'claimant' ? '#2563eb' : '#ea580c',
                textTransform: 'uppercase',
                letterSpacing: '0.025em',
                border: `1px solid ${element.burden_holder === 'claimant' ? '#dbeafe' : '#ffedd5'}`,
              }}
            >
              {element.burden_holder}
            </span>
            {!!element.has_shifted && (
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 700,
                  padding: '4px 8px',
                  borderRadius: '6px',
                  background: '#f0fdf4',
                  color: '#16a34a',
                  border: '1px solid #dcfce7',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <Icon name="ArrowRightLeft" size={10} />
                Shifted
              </span>
            )}
          </div>
        </div>

        <p
          style={{
            fontSize: '14px',
            color: '#4b5563',
            margin: '0 0 20px 0',
            lineHeight: '1.5',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {element.description || 'No description provided for this element.'}
        </p>

        <div style={{ marginBottom: '20px' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '8px',
            }}
          >
            <span
              style={{
                fontSize: '13px',
                fontWeight: 600,
                color: '#374151',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <Icon name="Database" size={14} />
              Evidence Weight
            </span>
            <span style={{ fontSize: '13px', fontWeight: 700, color: statusColor }}>
              {percentage}%
            </span>
          </div>
          <div
            style={{
              height: '10px',
              background: '#f3f4f6',
              borderRadius: '5px',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${percentage}%`,
                background: statusColor,
                borderRadius: '5px',
                transition: 'width 0.5s ease-out',
              }}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px' }}>
            <span style={{ fontSize: '11px', color: '#9ca3af' }}>
              {element.current_weight} points
            </span>
            <span style={{ fontSize: '11px', color: '#9ca3af' }}>
              Target: {element.required_weight}
            </span>
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            paddingTop: '16px',
            borderTop: '1px solid #f3f4f6',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                color: '#6b7280',
                fontSize: '13px',
              }}
            >
              <Icon name="FileText" size={14} />
              {element.evidence_count} items
            </div>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '12px',
                fontWeight: 600,
                color: statusColor,
              }}
            >
              <div
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  background: statusColor,
                }}
              />
              {STATUS_LABELS[element.status]}
            </div>
          </div>

          <button
            onClick={onAddWeight}
            style={{
              padding: '6px 12px',
              background: 'transparent',
              color: '#3b82f6',
              border: '1px solid #dbeafe',
              borderRadius: '6px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'background 0.2s',
            }}
            onMouseOver={(e) => (e.currentTarget.style.background = '#eff6ff')}
            onMouseOut={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <Icon name="Scale" size={14} />
            Add Weight
          </button>
        </div>
      </div>
    </div>
  );
}

function CreateElementDialog({
  projectId,
  onClose,
  onSuccess,
}: {
  projectId?: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    title: '',
    claim_type: 'Direct Discrimination',
    statutory_reference: '',
    description: '',
    burden_holder: 'claimant',
    required: true,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.title.trim()) {
      toast.error('Title is required');
      return;
    }

    try {
      setSaving(true);
      await api.createElement({
        ...formData,
        project_id: projectId,
      });
      toast.success('Element created successfully');
      onSuccess();
    } catch (err) {
      toast.error(`Failed to create element: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <DialogOverlay onClose={onClose}>
      <form onSubmit={handleSubmit} style={{ width: '500px' }}>
        <h2
          style={{
            margin: '0 0 24px 0',
            fontSize: '20px',
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <Icon name="PlusCircle" size={24} color="#3b82f6" />
          Create Burden Element
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <FormField label="Element Title" required>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="e.g. Less favourable treatment"
              style={inputStyle}
            />
          </FormField>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <FormField label="Claim Type">
              <select
                value={formData.claim_type}
                onChange={(e) => setFormData({ ...formData, claim_type: e.target.value })}
                style={inputStyle}
              >
                <option value="Direct Discrimination">Direct Discrimination</option>
                <option value="Indirect Discrimination">Indirect Discrimination</option>
                <option value="Harassment">Harassment</option>
                <option value="Victimisation">Victimisation</option>
                <option value="Unfair Dismissal">Unfair Dismissal</option>
                <option value="Contract Breach">Contract Breach</option>
              </select>
            </FormField>

            <FormField label="Statutory Reference">
              <input
                type="text"
                value={formData.statutory_reference}
                onChange={(e) => setFormData({ ...formData, statutory_reference: e.target.value })}
                placeholder="e.g. s.13 EqA 2010"
                style={inputStyle}
              />
            </FormField>
          </div>

          <FormField label="Primary Burden Holder">
            <div style={{ display: 'flex', gap: '12px' }}>
              <label style={radioContainerStyle(formData.burden_holder === 'claimant')}>
                <input
                  type="radio"
                  name="burden_holder"
                  checked={formData.burden_holder === 'claimant'}
                  onChange={() => setFormData({ ...formData, burden_holder: 'claimant' })}
                  style={{ display: 'none' }}
                />
                Claimant
              </label>
              <label style={radioContainerStyle(formData.burden_holder === 'respondent')}>
                <input
                  type="radio"
                  name="burden_holder"
                  checked={formData.burden_holder === 'respondent'}
                  onChange={() => setFormData({ ...formData, burden_holder: 'respondent' })}
                  style={{ display: 'none' }}
                />
                Respondent
              </label>
            </div>
          </FormField>

          <FormField label="Description">
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Describe the legal requirement for this element..."
              rows={4}
              style={{ ...inputStyle, resize: 'none' }}
            />
          </FormField>
        </div>

        <div
          style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '32px' }}
        >
          <button type="button" onClick={onClose} style={secondaryButtonStyle}>
            Cancel
          </button>
          <button type="submit" disabled={saving} style={primaryButtonStyle}>
            {saving ? 'Creating...' : 'Create Element'}
          </button>
        </div>
      </form>
    </DialogOverlay>
  );
}

function AddWeightDialog({
  elementId,
  onClose,
  onSuccess,
}: {
  elementId: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    weight: '25',
    source_type: 'document',
    source_id: 'auto-gen-' + Date.now(),
    source_title: '',
    excerpt: '',
    supports_burden_holder: true,
    analyst_notes: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.source_title.trim()) {
      toast.error('Source Title is required');
      return;
    }

    try {
      setSaving(true);
      await api.addEvidenceWeight({
        ...formData,
        element_id: elementId,
      });
      toast.success('Evidence weight added');
      onSuccess();
    } catch (err) {
      toast.error(`Failed to add weight: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <DialogOverlay onClose={onClose}>
      <form onSubmit={handleSubmit} style={{ width: '550px' }}>
        <h2
          style={{
            margin: '0 0 24px 0',
            fontSize: '20px',
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <Icon name="Scale" size={24} color="#f59e0b" />
          Add Evidence Weight
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <FormField label="Assigned Weight (Points)">
              <input
                type="number"
                value={formData.weight}
                onChange={(e) => setFormData({ ...formData, weight: e.target.value })}
                min="0"
                max="100"
                style={inputStyle}
              />
            </FormField>
            <FormField label="Source Type">
              <select
                value={formData.source_type}
                onChange={(e) => setFormData({ ...formData, source_type: e.target.value })}
                style={inputStyle}
              >
                <option value="document">Document</option>
                <option value="witness_statement">Witness Statement</option>
                <option value="email">Email / Slack</option>
                <option value="recording">Audio/Video</option>
                <option value="physical">Physical Evidence</option>
              </select>
            </FormField>
          </div>

          <FormField label="Source Title" required>
            <input
              type="text"
              value={formData.source_title}
              onChange={(e) => setFormData({ ...formData, source_title: e.target.value })}
              placeholder="e.g. Email from HR dated 2023-05-12"
              style={inputStyle}
            />
          </FormField>

          <FormField label="Key Excerpt">
            <textarea
              value={formData.excerpt}
              onChange={(e) => setFormData({ ...formData, excerpt: e.target.value })}
              placeholder="Paste the relevant text here..."
              rows={3}
              style={{ ...inputStyle, resize: 'none' }}
            />
          </FormField>

          <FormField label="Support Direction">
            <div style={{ display: 'flex', gap: '12px' }}>
              <label style={radioContainerStyle(formData.supports_burden_holder)}>
                <input
                  type="radio"
                  checked={formData.supports_burden_holder}
                  onChange={() => setFormData({ ...formData, supports_burden_holder: true })}
                  style={{ display: 'none' }}
                />
                Supports Holder
              </label>
              <label style={radioContainerStyle(!formData.supports_burden_holder)}>
                <input
                  type="radio"
                  checked={!formData.supports_burden_holder}
                  onChange={() => setFormData({ ...formData, supports_burden_holder: false })}
                  style={{ display: 'none' }}
                />
                Undermines Holder
              </label>
            </div>
          </FormField>

          <FormField label="Analyst Notes">
            <textarea
              value={formData.analyst_notes}
              onChange={(e) => setFormData({ ...formData, analyst_notes: e.target.value })}
              placeholder="Internal reasoning for this weight assignment..."
              rows={2}
              style={{ ...inputStyle, resize: 'none' }}
            />
          </FormField>
        </div>

        <div
          style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '32px' }}
        >
          <button type="button" onClick={onClose} style={secondaryButtonStyle}>
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            style={{ ...primaryButtonStyle, background: '#f59e0b' }}
          >
            {saving ? 'Applying...' : 'Apply Weight'}
          </button>
        </div>
      </form>
    </DialogOverlay>
  );
}

function DialogOverlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.5)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '20px',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'white',
          borderRadius: '20px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          padding: '32px',
          maxHeight: 'calc(100vh - 40px)',
          overflowY: 'auto',
          border: '1px solid #e2e8f0',
        }}
      >
        {children}
      </div>
    </div>
  );
}

function FormField({
  label,
  children,
  required,
}: {
  label: string;
  children: React.ReactNode;
  required?: boolean;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <label
        style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'flex', gap: '4px' }}
      >
        {label}
        {!!required && <span style={{ color: '#ef4444' }}>*</span>}
      </label>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 14px',
  borderRadius: '8px',
  border: '1px solid #d1d5db',
  fontSize: '14px',
  color: '#111827',
  background: '#ffffff',
  transition: 'border-color 0.2s',
  boxSizing: 'border-box',
};

const primaryButtonStyle: React.CSSProperties = {
  padding: '10px 20px',
  background: '#3b82f6',
  color: 'white',
  border: 'none',
  borderRadius: '8px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const secondaryButtonStyle: React.CSSProperties = {
  padding: '10px 20px',
  background: 'transparent',
  color: '#4b5563',
  border: '1px solid #d1d5db',
  borderRadius: '8px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const radioContainerStyle = (active: boolean): React.CSSProperties => ({
  flex: 1,
  padding: '10px',
  borderRadius: '8px',
  border: `2px solid ${active ? '#3b82f6' : '#e5e7eb'}`,
  background: active ? '#eff6ff' : 'transparent',
  color: active ? '#2563eb' : '#6b7280',
  fontSize: '13px',
  fontWeight: 700,
  textAlign: 'center',
  cursor: 'pointer',
  transition: 'all 0.2s',
});
