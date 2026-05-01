import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  Building2, TrendingUp, TrendingDown, Minus, Bell, Edit2, Trash2, MoreVertical,
  Search, X, Star, ArrowRight, AlertTriangle, ShieldCheck, FileText, Calendar,
  MapPin, Factory, ChevronDown, Filter, Grid, List, Plus, Check, Mail, Leaf,
  ExternalLink, Users2, Radio, Info, CheckCircle2,
} from 'lucide-react';
import { Card, Chip, RiskBadge } from '../components/shared';
import type { PageId } from '../components/Sidebar';
import { companyProfileFromAnalysis, loadCompanyAnalysis } from '../lib/analysis';

type WatchlistCompany = {
  id: string;
  name: string;
  abn: string;
  industry: string;
  score: number;
  riskLevel: 'Low' | 'Medium' | 'High' | 'Critical';
  change7d: number;
  confidence: number;
  lastUpdated: string;
  alerts: number;
  logo?: string;
};

const watchlistData: WatchlistCompany[] = [
  { id: '1', name: 'BHP Group Limited', abn: '49 004 028 077', industry: 'Mining & Resources', score: 78, riskLevel: 'High', change7d: 6, confidence: 91, lastUpdated: '2h ago', alerts: 2 },
  { id: '2', name: 'Woolworths Group', abn: '88 000 014 675', industry: 'Food Retail', score: 42, riskLevel: 'Medium', change7d: -2, confidence: 87, lastUpdated: '5h ago', alerts: 0 },
  { id: '3', name: 'Origin Energy', abn: '30 000 051 696', industry: 'Energy', score: 65, riskLevel: 'Medium', change7d: 1, confidence: 84, lastUpdated: '1d ago', alerts: 1 },
  { id: '4', name: 'Treasury Wine Estates', abn: '24 004 373 862', industry: 'Agriculture', score: 31, riskLevel: 'Low', change7d: -4, confidence: 89, lastUpdated: '3h ago', alerts: 0 },
  { id: '5', name: 'Fortescue Ltd', abn: '57 002 594 872', industry: 'Mining & Resources', score: 82, riskLevel: 'High', change7d: 8, confidence: 93, lastUpdated: '1h ago', alerts: 3 },
  { id: '6', name: 'Bega Cheese Limited', abn: '81 008 358 503', industry: 'Food Manufacturing', score: 28, riskLevel: 'Low', change7d: 0, confidence: 86, lastUpdated: '6h ago', alerts: 0 },
];

const recentUpdates = [
  { icon: AlertTriangle, tone: 'orange', title: 'Risk score increased from 72 to 78 — new evidence added', source: 'Risk engine', time: '2h ago' },
  { icon: FileText, tone: 'blue', title: 'New ASX filing mentions environmental compliance review', source: 'ASX', time: 'Yesterday' },
  { icon: Factory, tone: 'amber', title: 'Tier-1 supplier Greenfield Farms flagged for land clearing', source: 'Supply chain signal', time: '2 days ago' },
  { icon: ShieldCheck, tone: 'emerald', title: 'EPBC database updated — 1 new protected area overlap confirmed', source: 'Gov data', time: '3 days ago' },
  { icon: Bell, tone: 'rose', title: 'Alert triggered: score moved +6 in 7 days — above threshold', source: 'Alert engine', time: '4 days ago' },
  { icon: FileText, tone: 'stone', title: 'News article flagged: habitat risk near WA mining site', source: 'Media', time: '5 days ago' },
];

const scoreBreakdown = [
  { label: 'Direct operations', value: 22, color: '#0f766e' },
  { label: 'Supply chain', value: 18, color: '#0891b2' },
  { label: 'Protected area proximity', value: 15, color: '#65a30d' },
  { label: 'Controversy signals', value: 14, color: '#ea580c' },
  { label: 'Disclosure gap', value: 9, color: '#9333ea' },
];

export function Watchlist() {
  const navigate = useNavigate();
  const analysis = useMemo(() => loadCompanyAnalysis(), []);
  const latestCompany = useMemo<WatchlistCompany | null>(() => {
    if (!analysis?.resolution) return null;
    const profile = companyProfileFromAnalysis(analysis);
    return {
      id: 'latest-analysis',
      name: profile.name,
      abn: profile.abn,
      industry: profile.sector,
      score: profile.score,
      riskLevel: profile.riskLevel,
      change7d: 0,
      confidence: profile.confidence,
      lastUpdated: 'Latest search',
      alerts: profile.riskLevel === 'Critical' || profile.riskLevel === 'High' ? 1 : 0,
    };
  }, [analysis]);
  const dynamicWatchlist = useMemo(
    () => latestCompany
      ? [latestCompany, ...watchlistData.filter(company => company.abn !== latestCompany.abn)]
      : watchlistData,
    [latestCompany],
  );
  const [addCompanyOpen, setAddCompanyOpen] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState<WatchlistCompany | null>(dynamicWatchlist[0]);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterActive, setFilterActive] = useState('All');

  const filters = ['All', 'High Risk', 'Medium Risk', 'Low Risk', 'Alerts Active', 'Recently Updated'];

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#f5f3ee] via-[#eef1ec] to-[#e3ebe4]">
      <div className="max-w-[1600px] mx-auto px-6 py-6">

        {/* === PAGE HEADER === */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="text-[24px] text-stone-900 mb-1">My Watchlist</div>
            <div className="text-[13px] text-stone-600 mb-2">Track biodiversity risk changes across your saved companies</div>
            <div className="text-[11px] text-stone-500 flex items-center gap-2 flex-wrap">
              <span className="inline-flex items-center gap-1"><Star size={10} className="text-emerald-600" /> Watching {dynamicWatchlist.length} companies</span>
              <span className="w-1 h-1 rounded-full bg-stone-300" />
              <span className="inline-flex items-center gap-1"><Bell size={10} className="text-amber-600" /> 2 alerts active</span>
              <span className="w-1 h-1 rounded-full bg-stone-300" />
              <span>Last refreshed 3 mins ago</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button className="inline-flex items-center gap-1.5 px-4 h-10 rounded-lg border border-stone-200 bg-white hover:bg-stone-50 text-[13px] text-stone-700">
              <Bell size={14} /> Manage alerts
            </button>
            <button onClick={() => setAddCompanyOpen(true)} className="inline-flex items-center gap-1.5 px-4 h-10 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white text-[13px]">
              <Plus size={14} /> Add company
            </button>
          </div>
        </div>

        {/* === MAIN LAYOUT === */}
        <div className="grid grid-cols-12 gap-5">

          {/* === LEFT: WATCHLIST TABLE === */}
          <div className={`col-span-12 ${selectedCompany ? 'lg:col-span-8' : ''} transition-all duration-300`}>
            <Card className="p-5 flex flex-col h-[calc(100vh-140px)]">
              {/* TABLE TOOLBAR */}
              <div className="mb-6 shrink-0 flex flex-col gap-4 border-b border-stone-100 pb-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="relative w-full sm:max-w-md">
                    <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-stone-400" />
                    <input
                      type="text"
                      placeholder="Search companies by name, ABN, or industry..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-full h-10 pl-10 pr-4 rounded-lg border border-stone-200 text-[13px] bg-stone-50/50 focus:bg-white focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all placeholder:text-stone-400 shadow-sm"
                    />
                  </div>
                  
                  <div className="flex items-center gap-2 shrink-0">
                    <button className="inline-flex items-center gap-2 px-3 h-10 rounded-lg border border-stone-200 bg-white hover:bg-stone-50 text-[12.5px] font-medium text-stone-700 shadow-sm transition-colors">
                      <Filter size={14} className="text-stone-400" /> Sort: Risk score <ChevronDown size={14} className="text-stone-400 ml-1" />
                    </button>
                    <div className="flex items-center p-1 rounded-lg border border-stone-200 bg-stone-50 shadow-sm">
                      <button className="w-8 h-8 flex items-center justify-center rounded-md bg-white shadow-sm text-emerald-700 transition-all"><List size={16} /></button>
                      <button className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-white hover:text-stone-700 text-stone-400 transition-all"><Grid size={16} /></button>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <div className="text-[11px] font-bold text-stone-400 uppercase tracking-wider">Filters</div>
                  <div className="w-px h-4 bg-stone-200" />
                  <div className="flex items-center gap-2 flex-wrap">
                    {filters.map(f => (
                      <button
                        key={f}
                        onClick={() => setFilterActive(f)}
                        className={`px-3.5 h-7 rounded-full text-[12px] font-medium transition-all ${
                          filterActive === f
                            ? 'bg-emerald-700 text-white shadow-sm'
                            : 'bg-white border border-stone-200 text-stone-600 hover:bg-stone-50 hover:border-stone-300'
                        }`}
                      >
                        {f}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* WATCHLIST TABLE */}
              <div className="overflow-auto flex-1 -mx-5 px-5 pb-2 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar]:h-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-stone-200 [&::-webkit-scrollbar-thumb]:rounded-full hover:[&::-webkit-scrollbar-thumb]:bg-stone-300">
                <div className="min-w-[840px]">
                  {/* Table Header */}
                  <div className="sticky top-0 z-20 grid grid-cols-[minmax(240px,1fr)_100px_90px_90px_90px_80px_140px] gap-4 px-4 py-3 text-[11px] font-bold text-stone-500 uppercase tracking-wider border-b border-stone-200 bg-white/95 backdrop-blur-sm rounded-t-xl mb-2">
                    <div>Company Profile</div>
                    <div className="text-center">Risk Score</div>
                    <div className="text-center">7D Trend</div>
                    <div className="text-center">Confidence</div>
                    <div className="text-center">Updated</div>
                    <div className="text-center">Alerts</div>
                    <div className="text-right pr-2">Actions</div>
                  </div>

                  {/* Table Rows */}
                  <div className="flex flex-col gap-1.5">
                    {dynamicWatchlist.map(company => (
                      <button
                        key={company.id}
                        onClick={() => setSelectedCompany(company)}
                        className={`w-full text-left px-4 py-3.5 rounded-xl border transition-all group relative ${
                          selectedCompany?.id === company.id
                            ? 'border-emerald-500 bg-emerald-50/40 shadow-[0_2px_10px_-2px_rgba(16,185,129,0.15)] z-10'
                            : 'border-transparent hover:border-stone-200 hover:bg-stone-50 hover:shadow-sm bg-white'
                        }`}
                      >
                        {selectedCompany?.id === company.id && (
                          <div className="absolute left-0 top-3 bottom-3 w-1 bg-emerald-500 rounded-r-md" />
                        )}
                        
                        <div className="grid grid-cols-[minmax(240px,1fr)_100px_90px_90px_90px_80px_140px] gap-4 items-center">
                          {/* Logo & Company Info */}
                          <div className="flex items-center gap-3.5 min-w-0 pr-4">
                            <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 text-[12px] font-bold shadow-sm ${
                              selectedCompany?.id === company.id 
                                ? 'bg-gradient-to-br from-emerald-700 to-emerald-900 text-white' 
                                : 'bg-gradient-to-br from-stone-700 to-stone-900 text-white'
                            }`}>
                              {company.name.slice(0, 2).toUpperCase()}
                            </div>
                            <div className="min-w-0">
                              <div className="text-[14px] text-stone-900 font-semibold truncate mb-1">{company.name}</div>
                              <div className="flex items-center gap-2 text-[11.5px] text-stone-500">
                                <span className="truncate max-w-[120px] font-medium">{company.industry}</span>
                                <span className="w-1 h-1 rounded-full bg-stone-300 shrink-0" />
                                <span className="font-mono text-[10.5px]">ABN {company.abn}</span>
                              </div>
                            </div>
                          </div>

                          {/* Risk Score */}
                          <div className="flex flex-col items-center justify-center gap-1.5">
                            <div className="text-[18px] leading-none text-stone-900 tabular-nums font-bold">{company.score}</div>
                            <RiskBadge level={company.riskLevel} />
                          </div>

                          {/* Change */}
                          <div className="flex justify-center">
                            {company.change7d > 0 && (
                              <div className="inline-flex items-center gap-1 text-[12px] text-rose-700 font-bold bg-rose-50 px-2 py-1.5 rounded-md border border-rose-100">
                                <TrendingUp size={14} strokeWidth={2.5} /> +{company.change7d}
                              </div>
                            )}
                            {company.change7d < 0 && (
                              <div className="inline-flex items-center gap-1 text-[12px] text-emerald-700 font-bold bg-emerald-50 px-2 py-1.5 rounded-md border border-emerald-100">
                                <TrendingDown size={14} strokeWidth={2.5} /> {company.change7d}
                              </div>
                            )}
                            {company.change7d === 0 && (
                              <div className="text-[12px] text-stone-400 font-bold bg-stone-50 px-3 py-1.5 rounded-md border border-stone-100 inline-flex items-center">
                                <Minus size={14} strokeWidth={2.5} />
                              </div>
                            )}
                          </div>

                          {/* Confidence */}
                          <div className="flex justify-center">
                            <div className="inline-flex items-center gap-1.5 text-[12px] text-stone-600 font-medium tabular-nums bg-stone-50 px-2.5 py-1.5 rounded-md border border-stone-100">
                              <ShieldCheck size={14} className="text-emerald-600" /> {company.confidence}%
                            </div>
                          </div>

                          {/* Updated */}
                          <div className="text-[11.5px] text-stone-500 text-center font-medium bg-stone-50/50 py-1.5 px-2 rounded-md">
                            {company.lastUpdated}
                          </div>

                          {/* Alerts */}
                          <div className="flex justify-center">
                            {company.alerts > 0 ? (
                              <div className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-amber-50 border border-amber-200 text-amber-700 text-[11.5px] font-bold shadow-sm">
                                <Bell size={12} className="fill-amber-700" /> {company.alerts}
                              </div>
                            ) : (
                              <div className="text-stone-300 text-[12px] font-medium">-</div>
                            )}
                          </div>

                          {/* Actions */}
                          <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-stone-200/60 text-stone-500 transition-colors" title="Manage alerts" onClick={(e) => e.stopPropagation()}><Bell size={15} /></button>
                            <button className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-stone-200/60 text-stone-500 transition-colors" title="Edit company" onClick={(e) => e.stopPropagation()}><Edit2 size={15} /></button>
                            <button className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-rose-100 text-rose-600 transition-colors" title="Remove" onClick={(e) => e.stopPropagation()}><Trash2 size={15} /></button>
                            <button className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-stone-200/60 text-stone-500 transition-colors" title="More options" onClick={(e) => e.stopPropagation()}><MoreVertical size={15} /></button>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          </div>

          {/* === RIGHT: COMPANY DETAIL PANEL === */}
          {selectedCompany && (
            <div className="col-span-12 lg:col-span-4 animate-in fade-in slide-in-from-right-4 duration-300">
              <Card className="border-l-4 border-emerald-500 sticky top-6 flex flex-col h-[calc(100vh-140px)] overflow-hidden relative">
                <div className="absolute top-3 right-3 z-10">
                  <button onClick={() => setSelectedCompany(null)} className="w-8 h-8 flex items-center justify-center rounded-full bg-white/90 backdrop-blur-sm shadow-[0_2px_8px_-2px_rgba(0,0,0,0.1)] border border-stone-100 hover:bg-stone-50 text-stone-500 transition-all hover:scale-105 active:scale-95">
                    <X size={16} />
                  </button>
                </div>

                <div className="p-5 overflow-y-auto flex-1 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-stone-200 [&::-webkit-scrollbar-thumb]:rounded-full hover:[&::-webkit-scrollbar-thumb]:bg-stone-300">
                  {/* Company Identity */}
                  <div className="mb-5 pr-8 mt-1">
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-stone-700 to-stone-900 text-white flex items-center justify-center text-[14px] mb-3">
                    {selectedCompany.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="text-[17px] text-stone-900 font-medium mb-1">{selectedCompany.name}</div>
                  <div className="text-[11px] text-stone-500 mb-2">ABN {selectedCompany.abn}</div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <Chip tone="emerald">{selectedCompany.industry}</Chip>
                    <Chip tone="blue"><MapPin size={9} /> Melbourne, VIC</Chip>
                    <Chip tone="stone">Public</Chip>
                  </div>
                </div>

                {/* Risk Hero Block */}
                <div className="p-4 rounded-xl bg-gradient-to-br from-rose-50 to-orange-50 border border-rose-100 mb-5">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-[32px] leading-none text-stone-900 tabular-nums">{selectedCompany.score} <span className="text-[14px] text-stone-400">/ 100</span></div>
                    <RiskBadge level={selectedCompany.riskLevel} />
                  </div>
                  <div className="flex items-center gap-2 mb-3">
                    {selectedCompany.change7d !== 0 && (
                      <div className={`inline-flex items-center gap-1 text-[12px] ${selectedCompany.change7d > 0 ? 'text-rose-700' : 'text-emerald-700'}`}>
                        {selectedCompany.change7d > 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                        {selectedCompany.change7d > 0 ? '+' : ''}{selectedCompany.change7d} this week
                      </div>
                    )}
                    <div className="text-[11px] text-stone-500">{selectedCompany.confidence}% confidence</div>
                  </div>
                  <div className="text-[11.5px] text-stone-700 leading-relaxed">
                    Score of {selectedCompany.score} reflects elevated biodiversity risk based on spatial overlap, supplier exposure, and recent regulatory signals.
                  </div>
                </div>

                {/* Score Composition */}
                <div className="mb-5">
                  <div className="text-[11px] uppercase tracking-wider text-stone-500 mb-2">Score breakdown</div>
                  <div className="flex h-2 rounded-full overflow-hidden border border-stone-100 mb-2">
                    {scoreBreakdown.map(s => (
                      <div key={s.label} style={{ width: `${(s.value / selectedCompany.score) * 100}%`, background: s.color }} />
                    ))}
                  </div>
                  <div className="space-y-1">
                    {scoreBreakdown.map(s => (
                      <div key={s.label} className="flex items-center gap-2 text-[11px]">
                        <span className="w-2 h-2 rounded-sm" style={{ background: s.color }} />
                        <span className="flex-1 text-stone-600">{s.label}</span>
                        <span className="text-stone-700 tabular-nums">{s.value} pts</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Summary Bullets */}
                <div className="mb-5">
                  <div className="text-[11px] uppercase tracking-wider text-stone-500 mb-2">Key risks</div>
                  <ul className="space-y-2 text-[12px] text-stone-700">
                    <li className="flex gap-2"><span className="w-1 h-1 rounded-full bg-rose-500 mt-1.5 shrink-0" /> Operations near 4 EPBC-listed sensitive areas</li>
                    <li className="flex gap-2"><span className="w-1 h-1 rounded-full bg-amber-500 mt-1.5 shrink-0" /> Tier-1 supplier linked to land-clearing event in QLD</li>
                    <li className="flex gap-2"><span className="w-1 h-1 rounded-full bg-blue-500 mt-1.5 shrink-0" /> ASX filing noted TNFD alignment underway but incomplete</li>
                  </ul>
                </div>

                <div className="border-t border-stone-100 my-5" />

                {/* Recent Updates Feed */}
                <div className="mb-5">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="text-[12px] uppercase tracking-wider text-stone-600">Recent Updates</div>
                    <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  </div>
                  <div className="space-y-3 pb-4">
                    {recentUpdates.map((update, i) => {
                      const Icon = update.icon;
                      const tones: Record<string, string> = {
                        orange: 'bg-orange-100 text-orange-700',
                        blue: 'bg-blue-100 text-blue-700',
                        amber: 'bg-amber-100 text-amber-700',
                        emerald: 'bg-emerald-100 text-emerald-700',
                        rose: 'bg-rose-100 text-rose-700',
                        stone: 'bg-stone-100 text-stone-700',
                      };
                      return (
                        <div key={i} className="flex gap-2">
                          <div className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 ${tones[update.tone]}`}>
                            <Icon size={11} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-[11.5px] text-stone-900 leading-snug mb-1">{update.title}</div>
                            <div className="flex items-center gap-2 text-[10px] text-stone-500">
                              <span>{update.source}</span>
                              <span className="w-1 h-1 rounded-full bg-stone-300" />
                              <span>{update.time}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                </div>

                {/* Actions (Sticky at bottom) */}
                <div className="p-5 border-t border-stone-100 bg-white/95 backdrop-blur-sm shrink-0">
                  <div className="space-y-2">
                    <button onClick={() => navigate('/app/overview')} className="w-full h-10 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white text-[13px] inline-flex items-center justify-center gap-1.5 shadow-sm transition-colors">
                      View full company report <ArrowRight size={14} />
                    </button>
                    <button className="w-full h-10 rounded-lg border border-stone-200 hover:bg-stone-50 text-stone-700 text-[13px] inline-flex items-center justify-center gap-1.5 transition-colors">
                      <Users2 size={14} /> Compare with peers
                    </button>
                    <button className="w-full text-[12px] text-rose-600 hover:text-rose-700 mt-2 transition-colors">Remove from watchlist</button>
                  </div>
                </div>
              </Card>
            </div>
          )}
        </div>
      </div>

      {/* === ADD COMPANY MODAL === */}
      {addCompanyOpen && <AddCompanyModal onClose={() => setAddCompanyOpen(false)} />}
    </div>
  );
}

function AddCompanyModal({ onClose }: { onClose: () => void }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCompany, setSelectedCompany] = useState<WatchlistCompany | null>(null);
  const [notes, setNotes] = useState('');
  const [alertOnChange, setAlertOnChange] = useState(true);
  const [threshold, setThreshold] = useState('±5 pts');
  const [weeklyEmail, setWeeklyEmail] = useState(false);

  const searchResults: WatchlistCompany[] = searchQuery.length > 0 ? [
    { id: '7', name: 'Rio Tinto Limited', abn: '96 004 458 404', industry: 'Mining & Resources', score: 76, riskLevel: 'High', change7d: 3, confidence: 90, lastUpdated: '1h ago', alerts: 0 },
    { id: '8', name: 'Coles Group Limited', abn: '11 004 089 936', industry: 'Food Retail', score: 38, riskLevel: 'Medium', change7d: -1, confidence: 85, lastUpdated: '2h ago', alerts: 0 },
  ] : [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-stone-900/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-[560px] bg-white rounded-2xl shadow-2xl overflow-hidden max-h-[90vh] overflow-y-auto">

        <div className="p-6 border-b border-stone-100 sticky top-0 bg-white z-10">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[18px] text-stone-900">Add a company to your watchlist</div>
            <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-stone-100 text-stone-400">
              <X size={16} />
            </button>
          </div>
          <div className="text-[12.5px] text-stone-600">Search by company name, brand, or ABN</div>
        </div>

        <div className="p-6 space-y-5">
          {/* Search */}
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
            <input
              type="text"
              placeholder="e.g. BHP, Tim Tams, 12 345 678 901"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-12 pl-10 pr-4 rounded-lg border border-stone-200 text-[14px] focus:outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20"
            />
          </div>

          {/* Search Results */}
          {searchQuery && searchResults.length > 0 && !selectedCompany && (
            <div className="border border-stone-200 rounded-lg overflow-hidden">
              {searchResults.map(company => (
                <button
                  key={company.id}
                  onClick={() => setSelectedCompany(company)}
                  className="w-full text-left p-3 hover:bg-stone-50 border-b border-stone-100 last:border-0 flex items-center gap-3"
                >
                  <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-stone-700 to-stone-900 text-white flex items-center justify-center text-[11px] shrink-0">
                    {company.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <div className="text-[13px] text-stone-900 font-medium truncate">{company.name}</div>
                      <Chip tone="stone">{company.industry}</Chip>
                    </div>
                    <div className="text-[11px] text-stone-500">ABN {company.abn}</div>
                  </div>
                  <div className="text-center">
                    <div className="text-[18px] leading-none text-stone-900 tabular-nums">{company.score}</div>
                    <RiskBadge level={company.riskLevel} />
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* Selected Company */}
          {selectedCompany && (
            <>
              <div className="p-4 rounded-xl border border-emerald-200 bg-emerald-50/50 space-y-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-stone-700 to-stone-900 text-white flex items-center justify-center text-[13px]">
                    {selectedCompany.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex-1">
                    <div className="text-[14px] text-stone-900 font-medium mb-1">{selectedCompany.name}</div>
                    <div className="flex items-center gap-2">
                      <div className="text-[11px] text-stone-500">ABN {selectedCompany.abn}</div>
                      <Chip tone="emerald">{selectedCompany.industry}</Chip>
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-[22px] leading-none text-stone-900 tabular-nums">{selectedCompany.score}</div>
                    <RiskBadge level={selectedCompany.riskLevel} />
                  </div>
                </div>

                <div className="pt-4 border-t border-emerald-100 space-y-4">
                  <div>
                    <div className="text-[11px] font-medium text-emerald-800 mb-1.5">Private label or note (optional)</div>
                    <input
                      type="text"
                      placeholder="e.g. Portfolio holding, supplier review"
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      className="w-full h-10 px-3 rounded-lg border border-emerald-200 bg-white/60 text-[13px] focus:bg-white focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 placeholder:text-stone-400"
                    />
                  </div>

                  <div>
                    <div className="text-[11px] font-medium text-emerald-800 mb-1.5">Upload internal evidence (.pdf)</div>
                    <label className="flex items-center justify-center gap-2 w-full h-10 px-3 rounded-lg border border-dashed border-emerald-300 bg-white/40 hover:bg-white/80 hover:border-emerald-400 text-[12px] text-emerald-700 font-medium transition-colors cursor-pointer group">
                      <input type="file" accept=".pdf" className="hidden" />
                      <FileText size={14} className="group-hover:-translate-y-0.5 transition-transform" />
                      <span>Attach internal sustainability report</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Alert Preferences */}
              <div className="space-y-3 pt-2">
                <div className="text-[12px] uppercase tracking-wider text-stone-600 mb-4 font-bold">Alert preferences</div>

                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={alertOnChange}
                    onChange={(e) => setAlertOnChange(e.target.checked)}
                    className="mt-0.5 w-4 h-4 accent-emerald-600"
                  />
                  <div className="flex-1">
                    <div className="text-[13px] text-stone-900 font-medium mb-1">Notify me when risk score changes significantly</div>
                    {alertOnChange && (
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-[12px] text-stone-600">Alert me when score changes by:</span>
                        <select
                          value={threshold}
                          onChange={(e) => setThreshold(e.target.value)}
                          className="h-8 px-2 rounded-lg border border-stone-200 bg-white text-[12px] focus:outline-none focus:border-emerald-500 shadow-sm"
                        >
                          <option>±5 pts</option>
                          <option>±10 pts</option>
                          <option>any change</option>
                        </select>
                      </div>
                    )}
                  </div>
                </label>

                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={weeklyEmail}
                    onChange={(e) => setWeeklyEmail(e.target.checked)}
                    className="mt-0.5 w-4 h-4 accent-emerald-600"
                  />
                  <div className="text-[13px] text-stone-900 font-medium">Send me a weekly summary email</div>
                </label>
              </div>

              {/* Actions */}
              <div className="pt-6 border-t border-stone-100">
                <button onClick={onClose} className="w-full h-11 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white text-[14px] font-medium shadow-sm transition-colors mb-2">
                  Add to watchlist
                </button>
                <button onClick={onClose} className="w-full h-11 rounded-lg text-[13px] font-medium text-stone-600 hover:text-stone-900 hover:bg-stone-50 transition-colors">
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
