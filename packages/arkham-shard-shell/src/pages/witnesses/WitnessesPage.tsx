import React, { useState, useEffect, useCallback } from 'react';
import { Users, UserPlus, FileText, Shield, Search, Filter, ChevronRight, Trash2, Edit } from 'lucide-react';

interface Witness {
  id: string;
  name: string;
  role: string;
  party: string;
  status: string;
  organization?: string;
  position?: string;
  credibility_level: string;
  created_at: string;
}

const ROLE_LABELS: Record<string, string> = {
  claimant: 'Claimant',
  respondent_witness: 'Respondent',
  independent: 'Independent',
  expert: 'Expert',
  character: 'Character',
};

const STATUS_COLORS: Record<string, string> = {
  identified: '#6b7280',
  contacted: '#3b82f6',
  confirmed: '#10b981',
  statement_taken: '#8b5cf6',
  unavailable: '#ef4444',
};

const CREDIBILITY_COLORS: Record<string, string> = {
  high: '#10b981',
  medium: '#f59e0b',
  low: '#ef4444',
  unknown: '#6b7280',
};

export const WitnessesPage: React.FC = () => {
  const [witnesses, setWitnesses] = useState<Witness[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterParty, setFilterParty] = useState('');

  const fetchWitnesses = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (filterParty) params.set('party', filterParty);
      const res = await fetch(`/api/witnesses/?${params}`);
      const data = await res.json();
      setWitnesses(data.witnesses || []);
    } catch (err) {
      console.error('Failed to fetch witnesses:', err);
    } finally {
      setLoading(false);
    }
  }, [search, filterParty]);

  useEffect(() => { fetchWitnesses(); }, [fetchWitnesses]);

  return (
    <div style={{ padding: '24px', maxWidth: '1200px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Users size={24} /> Witnesses
          </h1>
          <p style={{ color: '#6b7280', marginTop: '4px' }}>
            Manage witnesses, statements, and cross-examination preparation
          </p>
        </div>
        <button
          style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            padding: '8px 16px', background: '#3b82f6', color: 'white',
            border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 500,
          }}
        >
          <UserPlus size={16} /> Add Witness
        </button>
      </div>

      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <Search size={16} style={{ position: 'absolute', left: '10px', top: '10px', color: '#9ca3af' }} />
          <input
            type="text" placeholder="Search witnesses..."
            value={search} onChange={e => setSearch(e.target.value)}
            style={{
              width: '100%', padding: '8px 8px 8px 32px',
              border: '1px solid #e5e7eb', borderRadius: '6px',
              background: 'var(--bg-secondary, #f9fafb)',
            }}
          />
        </div>
        <select
          value={filterParty} onChange={e => setFilterParty(e.target.value)}
          style={{ padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: '6px', background: 'var(--bg-secondary, #f9fafb)' }}
        >
          <option value="">All Parties</option>
          <option value="claimant">Claimant</option>
          <option value="respondent">Respondent</option>
          <option value="third_party">Third Party</option>
        </select>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '48px', color: '#6b7280' }}>Loading witnesses...</div>
      ) : witnesses.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '48px', color: '#6b7280' }}>
          <Users size={48} style={{ marginBottom: '12px', opacity: 0.3 }} />
          <p>No witnesses yet. Add your first witness to get started.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {witnesses.map(w => (
            <div
              key={w.id}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '12px 16px', border: '1px solid #e5e7eb', borderRadius: '8px',
                background: 'var(--bg-primary, white)', cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '8px', height: '8px', borderRadius: '50%',
                  background: STATUS_COLORS[w.status] || '#6b7280',
                }} />
                <div>
                  <div style={{ fontWeight: 600 }}>{w.name}</div>
                  <div style={{ fontSize: '13px', color: '#6b7280' }}>
                    {ROLE_LABELS[w.role] || w.role}
                    {w.organization && ` · ${w.organization}`}
                    {w.position && ` · ${w.position}`}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{
                  padding: '2px 8px', borderRadius: '12px', fontSize: '12px', fontWeight: 500,
                  background: `${CREDIBILITY_COLORS[w.credibility_level] || '#6b7280'}20`,
                  color: CREDIBILITY_COLORS[w.credibility_level] || '#6b7280',
                }}>
                  {w.credibility_level}
                </span>
                <span style={{
                  padding: '2px 8px', borderRadius: '12px', fontSize: '12px',
                  background: w.party === 'claimant' ? '#dbeafe' : '#fde8e8',
                  color: w.party === 'claimant' ? '#1e40af' : '#991b1b',
                }}>
                  {w.party}
                </span>
                <ChevronRight size={16} style={{ color: '#9ca3af' }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
