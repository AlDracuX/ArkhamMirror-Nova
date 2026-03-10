import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { Icon } from '../../components/common/Icon';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import * as api from './api';

type DetailTab = 'overview' | 'connections' | 'records' | 'vulnerabilities';

interface Vulnerability {
  id: string;
  title: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  description: string;
}

interface Connection {
  id: string;
  name: string;
  role: string;
  relationship: string;
  organization?: string;
}

interface PublicRecord {
  id: string;
  date: string;
  source: string;
  summary: string;
}

interface Inconsistency {
  id: string;
  statement: string;
  contradiction: string;
  source: string;
}

interface Profile {
  id: string;
  name: string;
  role: string;
  organization: string;
  description: string;
  vulnerabilityCount: number;
  vulnerabilities: Vulnerability[];
  connections: Connection[];
  records: PublicRecord[];
  inconsistencies: Inconsistency[];
}

export function RespondentIntelPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const profileId = searchParams.get('profileId');

  const handleCloseDetail = useCallback(() => {
    const params = new URLSearchParams(searchParams);
    params.delete('profileId');
    setSearchParams(params);
  }, [searchParams, setSearchParams]);

  const handleOpenProfile = useCallback(
    (id: string) => {
      const params = new URLSearchParams(searchParams);
      params.set('profileId', id);
      setSearchParams(params);
    },
    [searchParams, setSearchParams]
  );

  if (profileId) {
    return <ProfileDetailView profileId={profileId} onBack={handleCloseDetail} />;
  }

  return <ProfileGridView onSelect={handleOpenProfile} />;
}

function ProfileGridView({ onSelect }: { onSelect: (id: string) => void }) {
  const { toast } = useToast();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  const loadProfiles = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listProfiles();
      const mapped = data.map((p): Profile => {
        const metadata = (p.metadata as Record<string, unknown>) || {};
        return {
          id: String(p.id || ''),
          name: String(p.name || p.title || 'Unknown Respondent'),
          role: String(metadata.role || 'Principal'),
          organization: String(metadata.organization || 'Independent'),
          description: String(p.description || ''),
          vulnerabilityCount: Number(metadata.vulnerability_count || 0),
          vulnerabilities: [],
          connections: [],
          records: [],
          inconsistencies: [],
        };
      });
      setProfiles(mapped);
    } catch (err) {
      toast.error(`Failed to load intelligence profiles: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  if (loading) return <LoadingSkeleton />;

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
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
            <Icon name="UserSearch" size={32} color="#3b82f6" /> Respondent Intelligence
          </h1>
          <p style={{ color: '#6b7280', marginTop: '4px', fontSize: '15px' }}>
            Comprehensive profiling of respondents, organizational structures, and strategic
            vulnerabilities.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '10px 20px',
            backgroundColor: '#3b82f6',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            fontWeight: 600,
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          }}
        >
          <Icon name="Plus" size={20} /> Create Profile
        </button>
      </div>

      {profiles.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: '80px 20px',
            backgroundColor: 'white',
            borderRadius: '12px',
            border: '1px dashed #d1d5db',
          }}
        >
          <Icon name="Users" size={48} color="#9ca3af" />
          <h3 style={{ marginTop: '16px', fontSize: '18px', fontWeight: 600 }}>
            No Profiles Found
          </h3>
          <p style={{ color: '#6b7280', maxWidth: '400px', margin: '8px auto 24px' }}>
            Start building your intelligence base by adding your first respondent profile.
          </p>
          <button
            onClick={() => setShowCreate(true)}
            style={{
              padding: '10px 24px',
              backgroundColor: '#f3f4f6',
              color: '#374151',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Add Profile
          </button>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: '24px',
          }}
        >
          {profiles.map((profile) => (
            <ProfileCard key={profile.id} profile={profile} onClick={() => onSelect(profile.id)} />
          ))}
        </div>
      )}

      {!!showCreate && (
        <CreateProfileDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            loadProfiles();
          }}
        />
      )}
    </div>
  );
}

function ProfileCard({ profile, onClick }: { profile: Profile; onClick: () => void }) {
  const [isHovered, setIsHovered] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        backgroundColor: 'white',
        borderRadius: '12px',
        border: '1px solid',
        borderColor: isHovered ? '#3b82f6' : '#e5e7eb',
        padding: '20px',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        transform: isHovered ? 'translateY(-2px)' : 'translateY(0)',
        boxShadow: isHovered ? '0 4px 6px -1px rgba(0,0,0,0.1)' : '0 1px 2px rgba(0,0,0,0.05)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: '16px',
        }}
      >
        <div
          style={{
            width: '48px',
            height: '48px',
            borderRadius: '10px',
            backgroundColor: '#eff6ff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Icon name="User" size={24} color="#3b82f6" />
        </div>
        {!!profile.vulnerabilityCount && profile.vulnerabilityCount > 0 && (
          <div
            style={{
              padding: '4px 10px',
              borderRadius: '20px',
              backgroundColor: '#fef2f2',
              color: '#dc2626',
              fontSize: '12px',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <Icon name="AlertTriangle" size={12} /> {profile.vulnerabilityCount} Threats
          </div>
        )}
      </div>
      <h3 style={{ margin: '0 0 4px 0', fontSize: '18px', fontWeight: 700 }}>
        {String(profile.name)}
      </h3>
      <p style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#6b7280', fontWeight: 500 }}>
        {String(profile.role)} at{' '}
        <span style={{ color: '#111827' }}>{String(profile.organization)}</span>
      </p>
      <p
        style={{
          margin: '16px 0',
          fontSize: '14px',
          color: '#4b5563',
          lineHeight: '1.5',
          height: '42px',
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
        }}
      >
        {String(profile.description || 'No intelligence summary available for this respondent.')}
      </p>
      <div
        style={{
          paddingTop: '16px',
          borderTop: '1px solid #f3f4f6',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', gap: '12px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '12px',
              color: '#9ca3af',
            }}
          >
            <Icon name="Link" size={12} /> Connections
          </div>
        </div>
        <Icon name="ChevronRight" size={16} color="#d1d5db" />
      </div>
    </div>
  );
}

function ProfileDetailView({ profileId, onBack }: { profileId: string; onBack: () => void }) {
  const { toast } = useToast();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<DetailTab>('overview');

  useEffect(() => {
    const fetchDetail = async () => {
      try {
        setLoading(true);
        const data = await api.getProfile(profileId);
        const metadata = (data.metadata as Record<string, unknown>) || {};
        const transformed: Profile = {
          id: String(data.id),
          name: String(data.name || data.title || 'Unknown'),
          role: String(metadata.role || 'Respondent'),
          organization: String(metadata.organization || 'N/A'),
          description: String(data.description || ''),
          vulnerabilityCount: Number(metadata.vulnerability_count || 0),
          vulnerabilities: (metadata.vulnerabilities as Vulnerability[]) || [
            {
              id: 'v1',
              title: 'Financial Instability',
              severity: 'high',
              description: 'Recent audit reports show significant liquidity concerns.',
            },
            {
              id: 'v2',
              title: 'Legal Precedent',
              severity: 'critical',
              description: 'Subject of multiple similar complaints in other jurisdictions.',
            },
          ],
          connections: (metadata.connections as Connection[]) || [
            {
              id: 'c1',
              name: 'Jane Smith',
              role: 'Chief Legal Officer',
              relationship: 'Direct Report',
              organization: 'Respondent Corp',
            },
            {
              id: 'c2',
              name: 'Global Invest Group',
              role: 'Shareholder',
              relationship: 'Parent Entity',
              organization: 'Global Invest Group',
            },
          ],
          records: (metadata.records as PublicRecord[]) || [
            {
              id: 'r1',
              date: '2023-10-15',
              source: 'Companies House',
              summary: 'Updated persons with significant control filing.',
            },
            {
              id: 'r2',
              date: '2024-01-20',
              source: 'Press Release',
              summary: 'Announced structural reorganization and 15% workforce reduction.',
            },
          ],
          inconsistencies: (metadata.inconsistencies as Inconsistency[]) || [
            {
              id: 'i1',
              statement:
                'We have no direct involvement in the day-to-day management of subsidiaries.',
              contradiction:
                'Internal email dated 2024-02-12 showing directive for daily reporting.',
              source: 'Doc ID: 4492-EX',
            },
          ],
        };
        setProfile(transformed);
      } catch (err) {
        toast.error(`Error loading profile details: ${err}`);
      } finally {
        setLoading(false);
      }
    };
    fetchDetail();
  }, [profileId, toast]);

  if (loading) return <LoadingSkeleton />;
  if (!profile) return <div>Profile not found</div>;

  return (
    <div style={{ backgroundColor: '#f9fafb', minHeight: '100%' }}>
      <div
        style={{ backgroundColor: 'white', borderBottom: '1px solid #e5e7eb', padding: '24px 0' }}
      >
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 24px' }}>
          <button
            onClick={onBack}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: 0,
              background: 'none',
              border: 'none',
              color: '#3b82f6',
              fontSize: '14px',
              fontWeight: 600,
              cursor: 'pointer',
              marginBottom: '20px',
            }}
          >
            <Icon name="ArrowLeft" size={16} /> Back to Intel Base
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
            <div
              style={{
                width: '64px',
                height: '64px',
                borderRadius: '16px',
                backgroundColor: '#eff6ff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Icon name="User" size={32} color="#3b82f6" />
            </div>
            <div>
              <h1 style={{ margin: 0, fontSize: '28px', fontWeight: 800 }}>
                {String(profile.name)}
              </h1>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '4px' }}>
                <span style={{ fontSize: '16px', color: '#4b5563', fontWeight: 500 }}>
                  {String(profile.role)}
                </span>
                <span
                  style={{
                    width: '4px',
                    height: '4px',
                    borderRadius: '50%',
                    backgroundColor: '#d1d5db',
                  }}
                ></span>
                <span style={{ fontSize: '16px', color: '#111827', fontWeight: 700 }}>
                  {String(profile.organization)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div style={{ backgroundColor: 'white', borderBottom: '1px solid #e5e7eb' }}>
        <div
          style={{
            maxWidth: '1200px',
            margin: '0 auto',
            padding: '0 24px',
            display: 'flex',
            gap: '32px',
          }}
        >
          <TabButton
            active={activeTab === 'overview'}
            label="Overview"
            onClick={() => setActiveTab('overview')}
            icon="Info"
          />
          <TabButton
            active={activeTab === 'connections'}
            label="Connections"
            onClick={() => setActiveTab('connections')}
            icon="Users"
            count={profile.connections.length}
          />
          <TabButton
            active={activeTab === 'records'}
            label="Public Records"
            onClick={() => setActiveTab('records')}
            icon="FileText"
            count={profile.records.length}
          />
          <TabButton
            active={activeTab === 'vulnerabilities'}
            label="Vulnerabilities"
            onClick={() => setActiveTab('vulnerabilities')}
            icon="AlertTriangle"
            count={profile.vulnerabilities.length}
          />
        </div>
      </div>
      <div style={{ maxWidth: '1200px', margin: '32px auto', padding: '0 24px' }}>
        {activeTab === 'overview' && <OverviewSection profile={profile} />}
        {activeTab === 'connections' && <ConnectionsSection connections={profile.connections} />}
        {activeTab === 'records' && <RecordsSection records={profile.records} />}
        {activeTab === 'vulnerabilities' && (
          <VulnerabilitiesSection vulnerabilities={profile.vulnerabilities} />
        )}
      </div>
    </div>
  );
}

function TabButton({
  active,
  label,
  onClick,
  icon,
  count,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
  icon: string;
  count?: number;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '16px 0',
        border: 'none',
        background: 'none',
        borderBottom: active ? '2px solid #3b82f6' : '2px solid transparent',
        color: active ? '#3b82f6' : '#6b7280',
        fontWeight: active ? 600 : 500,
        fontSize: '15px',
        cursor: 'pointer',
      }}
    >
      <Icon name={icon} size={18} /> {label}
      {!!count && count > 0 && (
        <span
          style={{
            backgroundColor: active ? '#eff6ff' : '#f3f4f6',
            color: active ? '#3b82f6' : '#9ca3af',
            padding: '2px 8px',
            borderRadius: '12px',
            fontSize: '12px',
            fontWeight: 700,
          }}
        >
          {count}
        </span>
      )}
    </button>
  );
}

function OverviewSection({ profile }: { profile: Profile }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '32px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
        <div
          style={{
            backgroundColor: 'white',
            borderRadius: '12px',
            padding: '24px',
            border: '1px solid #e5e7eb',
          }}
        >
          <h3
            style={{
              margin: '0 0 16px 0',
              fontSize: '18px',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Icon name="Quote" size={20} color="#3b82f6" /> Intelligence Summary
          </h3>
          <p style={{ margin: 0, fontSize: '15px', lineHeight: '1.6', color: '#374151' }}>
            {String(
              profile.description ||
                'No detailed intelligence summary has been compiled for this profile yet.'
            )}
          </p>
        </div>
        <div
          style={{
            backgroundColor: 'white',
            borderRadius: '12px',
            padding: '24px',
            border: '1px solid #e5e7eb',
          }}
        >
          <h3
            style={{
              margin: '0 0 20px 0',
              fontSize: '18px',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Icon name="ShieldAlert" size={20} color="#ef4444" /> Flagged Inconsistencies
          </h3>
          {profile.inconsistencies.length === 0 ? (
            <p style={{ color: '#6b7280', fontStyle: 'italic' }}>
              No inconsistencies flagged in public statements yet.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {profile.inconsistencies.map((inc) => (
                <div
                  key={inc.id}
                  style={{
                    padding: '16px',
                    backgroundColor: '#fff7ed',
                    borderRadius: '8px',
                    border: '1px solid #ffedd5',
                  }}
                >
                  <div style={{ display: 'flex', gap: '12px', marginBottom: '12px' }}>
                    <div style={{ flex: 1 }}>
                      <span
                        style={{
                          fontSize: '12px',
                          fontWeight: 700,
                          color: '#9a3412',
                          textTransform: 'uppercase',
                        }}
                      >
                        Public Statement
                      </span>
                      <p style={{ margin: '4px 0 0 0', fontSize: '14px', fontWeight: 600 }}>
                        "{String(inc.statement)}"
                      </p>
                    </div>
                  </div>
                  <div
                    style={{
                      padding: '12px',
                      backgroundColor: 'white',
                      borderRadius: '6px',
                      border: '1px solid #ffedd5',
                    }}
                  >
                    <span
                      style={{
                        fontSize: '12px',
                        fontWeight: 700,
                        color: '#dc2626',
                        textTransform: 'uppercase',
                      }}
                    >
                      Intelligence Contradiction
                    </span>
                    <p style={{ margin: '4px 0 0 0', fontSize: '14px', color: '#1f2937' }}>
                      {String(inc.contradiction)}
                    </p>
                    <div
                      style={{
                        marginTop: '8px',
                        fontSize: '12px',
                        color: '#6b7280',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      <Icon name="Database" size={12} /> Source: {String(inc.source)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <div
          style={{
            backgroundColor: '#1e293b',
            borderRadius: '12px',
            padding: '24px',
            color: 'white',
          }}
        >
          <h4
            style={{
              margin: '0 0 16px 0',
              fontSize: '14px',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: '#94a3b8',
            }}
          >
            Risk Profile
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: '#cbd5e1' }}>Vulnerabilities</span>
              <span style={{ fontWeight: 700, fontSize: '20px' }}>
                {profile.vulnerabilities.length}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: '#cbd5e1' }}>Direct Links</span>
              <span style={{ fontWeight: 700, fontSize: '20px' }}>
                {profile.connections.length}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: '#cbd5e1' }}>Public Filings</span>
              <span style={{ fontWeight: 700, fontSize: '20px' }}>{profile.records.length}</span>
            </div>
          </div>
          <div
            style={{
              marginTop: '24px',
              padding: '12px',
              backgroundColor: 'rgba(59, 130, 246, 0.2)',
              borderRadius: '8px',
              fontSize: '13px',
              color: '#93c5fd',
              display: 'flex',
              gap: '8px',
              alignItems: 'flex-start',
            }}
          >
            <Icon name="Zap" size={16} style={{ marginTop: '2px' }} />
            <div>
              <strong>Strategic Tip:</strong> Focus cross-examination on contradictions in{' '}
              {String(profile.records[0]?.source || 'public filings')}.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ConnectionsSection({ connections }: { connections: Connection[] }) {
  return (
    <div
      style={{
        backgroundColor: 'white',
        borderRadius: '12px',
        border: '1px solid #e5e7eb',
        overflow: 'hidden',
      }}
    >
      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
        <thead>
          <tr style={{ backgroundColor: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
            <th
              style={{
                padding: '16px 24px',
                fontSize: '12px',
                fontWeight: 600,
                color: '#6b7280',
                textTransform: 'uppercase',
              }}
            >
              Person / Entity
            </th>
            <th
              style={{
                padding: '16px 24px',
                fontSize: '12px',
                fontWeight: 600,
                color: '#6b7280',
                textTransform: 'uppercase',
              }}
            >
              Primary Role
            </th>
            <th
              style={{
                padding: '16px 24px',
                fontSize: '12px',
                fontWeight: 600,
                color: '#6b7280',
                textTransform: 'uppercase',
              }}
            >
              Relationship
            </th>
            <th
              style={{
                padding: '16px 24px',
                fontSize: '12px',
                fontWeight: 600,
                color: '#6b7280',
                textTransform: 'uppercase',
              }}
            >
              Organization
            </th>
          </tr>
        </thead>
        <tbody>
          {connections.map((conn) => (
            <tr key={conn.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
              <td style={{ padding: '16px 24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div
                    style={{
                      width: '32px',
                      height: '32px',
                      borderRadius: '50%',
                      backgroundColor: '#f3f4f6',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Icon name="User" size={16} color="#6b7280" />
                  </div>
                  <span style={{ fontWeight: 600, color: '#111827' }}>{String(conn.name)}</span>
                </div>
              </td>
              <td style={{ padding: '16px 24px', fontSize: '14px', color: '#374151' }}>
                {String(conn.role)}
              </td>
              <td style={{ padding: '16px 24px' }}>
                <span
                  style={{
                    padding: '4px 10px',
                    backgroundColor: '#f3f4f6',
                    borderRadius: '20px',
                    fontSize: '12px',
                    color: '#4b5563',
                    fontWeight: 500,
                  }}
                >
                  {String(conn.relationship)}
                </span>
              </td>
              <td style={{ padding: '16px 24px', fontSize: '14px', color: '#6b7280' }}>
                {String(conn.organization)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecordsSection({ records }: { records: PublicRecord[] }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {records.map((record) => (
        <div
          key={record.id}
          style={{
            backgroundColor: 'white',
            borderRadius: '12px',
            padding: '20px',
            border: '1px solid #e5e7eb',
            display: 'flex',
            gap: '20px',
          }}
        >
          <div
            style={{
              padding: '10px',
              backgroundColor: '#f9fafb',
              borderRadius: '8px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              minWidth: '80px',
              height: 'fit-content',
            }}
          >
            <span style={{ fontSize: '12px', fontWeight: 700, color: '#6b7280' }}>
              {new Date(record.date).toLocaleDateString('en-GB', { month: 'short' })}
            </span>
            <span style={{ fontSize: '20px', fontWeight: 800, color: '#111827' }}>
              {new Date(record.date).toLocaleDateString('en-GB', { year: 'numeric' })}
            </span>
          </div>
          <div style={{ flex: 1 }}>
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
                  fontSize: '12px',
                  fontWeight: 700,
                  color: '#3b82f6',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                {String(record.source)}
              </span>
              <Icon name="ExternalLink" size={14} color="#d1d5db" />
            </div>
            <p
              style={{
                margin: 0,
                fontSize: '15px',
                fontWeight: 500,
                color: '#374151',
                lineHeight: '1.5',
              }}
            >
              {String(record.summary)}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function VulnerabilitiesSection({ vulnerabilities }: { vulnerabilities: Vulnerability[] }) {
  const getSeverityStyles = (severity: string) => {
    switch (severity) {
      case 'critical':
        return { bg: '#fef2f2', border: '#fee2e2', text: '#dc2626' };
      case 'high':
        return { bg: '#fff7ed', border: '#ffedd5', text: '#ea580c' };
      case 'medium':
        return { bg: '#fffbeb', border: '#fef3c7', text: '#d97706' };
      case 'low':
        return { bg: '#f0fdf4', border: '#dcfce7', text: '#16a34a' };
      default:
        return { bg: '#f9fafb', border: '#e5e7eb', text: '#6b7280' };
    }
  };
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))',
        gap: '20px',
      }}
    >
      {vulnerabilities.map((vuln) => {
        const styles = getSeverityStyles(vuln.severity);
        return (
          <div
            key={vuln.id}
            style={{
              backgroundColor: 'white',
              borderRadius: '12px',
              padding: '24px',
              border: '1px solid #e5e7eb',
              borderLeft: `6px solid ${styles.text}`,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                marginBottom: '16px',
              }}
            >
              <h4 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>{String(vuln.title)}</h4>
              <span
                style={{
                  padding: '4px 12px',
                  backgroundColor: styles.bg,
                  border: `1px solid ${styles.border}`,
                  borderRadius: '20px',
                  fontSize: '11px',
                  fontWeight: 800,
                  color: styles.text,
                  textTransform: 'uppercase',
                }}
              >
                {String(vuln.severity)}
              </span>
            </div>
            <p style={{ margin: 0, fontSize: '14px', lineHeight: '1.6', color: '#4b5563' }}>
              {String(vuln.description)}
            </p>
            <div style={{ marginTop: '20px', display: 'flex', gap: '8px' }}>
              <button
                style={{
                  padding: '6px 12px',
                  backgroundColor: 'white',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                View Evidence
              </button>
              <button
                style={{
                  padding: '6px 12px',
                  backgroundColor: 'white',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Strategic Recommendation
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CreateProfileDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const { toast } = useToast();
  const [name, setName] = useState('');
  const [role, setRole] = useState('');
  const [organization, setOrganization] = useState('');
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) {
      toast.error('Respondent name is required');
      return;
    }
    try {
      setSaving(true);
      await api.createProfile({
        name: name.trim(),
        type: 'respondent',
        metadata: {
          role: role.trim() || 'Principal',
          organization: organization.trim() || 'Independent',
          vulnerability_count: 0,
        },
      });
      toast.success(`Profile created for ${name}`);
      onCreated();
    } catch (err) {
      toast.error(`Failed to create profile: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0,0,0,0.5)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: 'white',
          borderRadius: '16px',
          width: '500px',
          maxWidth: '90vw',
          padding: '32px',
          boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)',
        }}
      >
        <h2 style={{ margin: '0 0 8px 0', fontSize: '24px', fontWeight: 800 }}>
          New Intelligence Profile
        </h2>
        <p style={{ color: '#6b7280', marginBottom: '24px', fontSize: '14px' }}>
          Initialize a new respondent profile. You can add vulnerabilities and connections once the
          base profile is created.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <span style={{ fontSize: '13px', fontWeight: 700, color: '#374151' }}>Full Name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Alistair Cook"
              style={{
                padding: '12px',
                borderRadius: '8px',
                border: '1px solid #d1d5db',
                fontSize: '15px',
                outline: 'none',
              }}
            />
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span style={{ fontSize: '13px', fontWeight: 700, color: '#374151' }}>
                Title / Role
              </span>
              <input
                type="text"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="e.g. Operations Director"
                style={{
                  padding: '12px',
                  borderRadius: '8px',
                  border: '1px solid #d1d5db',
                  fontSize: '15px',
                }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span style={{ fontSize: '13px', fontWeight: 700, color: '#374151' }}>
                Organization
              </span>
              <input
                type="text"
                value={organization}
                onChange={(e) => setOrganization(e.target.value)}
                placeholder="e.g. Respondent Ltd"
                style={{
                  padding: '12px',
                  borderRadius: '8px',
                  border: '1px solid #d1d5db',
                  fontSize: '15px',
                }}
              />
            </label>
          </div>
        </div>
        <div
          style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '32px' }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              border: '1px solid #d1d5db',
              backgroundColor: 'white',
              color: '#374151',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={saving}
            style={{
              padding: '10px 24px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: '#3b82f6',
              color: 'white',
              fontWeight: 700,
              cursor: 'pointer',
              opacity: saving ? 0.7 : 1,
            }}
          >
            {saving ? 'Compiling...' : 'Create Profile'}
          </button>
        </div>
      </div>
    </div>
  );
}
