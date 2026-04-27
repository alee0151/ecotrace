import { useState } from 'react';
import { MapPin, Layers, Ruler, AlertTriangle, FileText, ExternalLink, X, Trees, Bird, Droplets, Siren, ShieldAlert, Waves, Leaf, Fish } from 'lucide-react';
import { ImageWithFallback } from '../components/figma/ImageWithFallback';
import { Card, Chip, RiskBadge, Confidence, SectionTitle } from '../components/shared';

const sites = [
  { id: 's1', name: 'Olympic Dam', state: 'SA', level: 'High' as const, x: 52, y: 64, type: 'Mine', km: 2.1 },
  { id: 's2', name: 'Mount Whaleback', state: 'WA', level: 'High' as const, x: 24, y: 40, type: 'Mine', km: 3.4 },
  { id: 's3', name: 'Port Hedland', state: 'WA', level: 'Medium' as const, x: 26, y: 28, type: 'Port', km: 6.2 },
  { id: 's4', name: 'Olympic Dam Tailings', state: 'SA', level: 'Critical' as const, x: 54, y: 66, type: 'Tailings', km: 0.8 },
  { id: 's5', name: 'Nickel West — Mt Keith', state: 'WA', level: 'Medium' as const, x: 30, y: 50, type: 'Mine', km: 4.5 },
];

const protectedAreas = [
  { id: 'p1', name: 'Karijini NP', x: 28, y: 42, kind: 'National Park' },
  { id: 'p2', name: 'Lake Eyre Basin', x: 56, y: 58, kind: 'RAMSAR' },
  { id: 'p3', name: 'Fortescue Marsh', x: 29, y: 38, kind: 'Wetland' },
];

const evidence = [
  { id: 'e1', type: 'EPBC', title: 'EPBC 2025/09421 — Expansion referral', date: '14 Apr 2026', conf: 92, source: 'Dept of Climate Change' },
  { id: 'e2', type: 'Audit', title: 'Turbidity breach, Port Hedland shipping channel', date: '21 Mar 2026', conf: 86, source: 'WA EPA' },
  { id: 'e3', type: 'Science', title: 'Greater Bilby population decline — Pilbara survey', date: '02 Mar 2026', conf: 78, source: 'CSIRO' },
  { id: 'e4', type: 'News', title: 'Traditional Owners raise concern over cultural site', date: '10 Feb 2026', conf: 72, source: 'ABC News' },
];

export function Analyse() {
  const [selected, setSelected] = useState<string | null>(null);
  const site = sites.find(s => s.id === selected);

  return (
    <div className="relative h-[calc(100vh-65px)] overflow-hidden">
      <div className="h-full overflow-y-auto relative bg-gradient-to-b from-[#f5f3ee] via-[#eef1ec] to-[#e3ebe4]">
        <div className="absolute top-6 right-8 text-[10px] font-mono tracking-[0.25em] uppercase text-emerald-800/60 pointer-events-none">§ 02 · ANALYSE</div>
        <div className="p-8 relative">
        <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-stone-500 mb-3">32°30′S · 137°45′E — OLYMPIC DAM · SA</div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-stone-400">Analyse · BHP Group</div>
            <div className="text-[22px] text-stone-900">Spatial & <span className="italic text-emerald-700">evidence</span> analysis</div>
          </div>
          <div className="flex items-center gap-2">
            <button className="inline-flex items-center gap-1.5 px-3 h-9 rounded-lg border border-stone-200 hover:bg-stone-50 text-sm"><Layers size={14} /> Layers</button>
            <button className="inline-flex items-center gap-1.5 px-3 h-9 rounded-lg border border-stone-200 hover:bg-stone-50 text-sm"><Ruler size={14} /> Measure</button>
          </div>
        </div>

        <Card className="p-0 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-stone-100">
            <div className="flex gap-1.5">
              <Chip tone="emerald">Operational sites (5)</Chip>
              <Chip tone="blue">Protected areas (3)</Chip>
              <Chip tone="amber">5 km buffer</Chip>
            </div>
            <div className="text-[11px] text-stone-500">Projection: GDA2020 Albers</div>
          </div>
          <div className="relative h-[420px] bg-gradient-to-br from-emerald-50 via-stone-50 to-blue-50">
            <svg className="absolute inset-0 w-full h-full" preserveAspectRatio="none">
              <defs>
                <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#e7e5e4" strokeWidth="1" />
                </pattern>
              </defs>
                            <foreignObject x="0" y="0" width="100%" height="100%" opacity="0.5" className="mix-blend-luminosity">
                <iframe
                  width="100%"
                  height="100%"
                  frameBorder="0"
                  scrolling="no"
                  marginHeight={0}
                  marginWidth={0}
                  src="https://www.openstreetmap.org/export/embed.html?bbox=112.0,-44.0,154.0,-10.0&amp;layer=mapnik"
                  style={{ border: 0, pointerEvents: 'none' }}
                />
              </foreignObject>
              <rect width="100%" height="100%" fill="url(#grid)" />
              <path d="M 10% 20% Q 30% 10% 50% 25% T 90% 30% L 90% 80% Q 60% 90% 40% 80% T 10% 85% Z" fill="rgba(16,185,129,0.08)" stroke="rgba(16,185,129,0.3)" />
            </svg>
            {protectedAreas.map(p => (
              <div key={p.id} className="absolute" style={{ left: `${p.x}%`, top: `${p.y}%` }}>
                <div className="w-20 h-20 -translate-x-1/2 -translate-y-1/2 rounded-full bg-emerald-500/10 border-2 border-dashed border-emerald-400/70" />
                <div className="absolute -translate-x-1/2 mt-1 text-[10px] text-emerald-800 bg-white/80 px-1.5 py-0.5 rounded whitespace-nowrap" style={{ top: '50%', left: '50%' }}>{p.name}</div>
              </div>
            ))}
            {sites.map(s => {
              const active = selected === s.id;
              const color = s.level === 'Critical' ? 'bg-rose-500' : s.level === 'High' ? 'bg-orange-500' : s.level === 'Medium' ? 'bg-amber-500' : 'bg-emerald-500';
              return (
                <button
                  key={s.id}
                  onClick={() => setSelected(s.id)}
                  className="absolute -translate-x-1/2 -translate-y-1/2 group"
                  style={{ left: `${s.x}%`, top: `${s.y}%` }}
                >
                  <div className={`w-4 h-4 rounded-full ${color} ring-4 ring-white shadow ${active ? 'scale-150' : ''} transition`} />
                  {active && (
                    <div className="absolute left-1/2 -translate-x-1/2 mt-2 whitespace-nowrap bg-stone-900 text-white text-[11px] px-2 py-1 rounded">
                      {s.name} · {s.km}km to PA
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </Card>

        <div className="mt-5 grid grid-cols-3 gap-4">
          <Card className="p-4"><div className="flex items-center gap-2 text-stone-600 text-[12px]"><Trees size={14} /> Land-use overlap</div><div className="text-[22px] text-stone-900 mt-1">3.2 ha</div><div className="text-[11px] text-stone-500">within 5 km of protected areas</div></Card>
          <Card className="p-4"><div className="flex items-center gap-2 text-stone-600 text-[12px]"><Bird size={14} /> Species exposure</div><div className="text-[22px] text-stone-900 mt-1">17</div><div className="text-[11px] text-stone-500">IUCN-listed within buffer</div></Card>
          <Card className="p-4"><div className="flex items-center gap-2 text-stone-600 text-[12px]"><Droplets size={14} /> Water stress</div><div className="text-[22px] text-stone-900 mt-1">Very High</div><div className="text-[11px] text-stone-500">WRI Aqueduct 4.0</div></Card>
        </div>

        <div className="mt-6">
          <SectionTitle title="Claim-linked evidence" action={<button className="text-[11px] text-emerald-700 hover:underline">Open provenance graph</button>} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {evidence.map(e => (
              <Card key={e.id} className="p-4">
                <div className="flex items-center gap-2 mb-1.5">
                  <Chip tone={e.type === 'EPBC' ? 'rose' : e.type === 'Audit' ? 'amber' : e.type === 'Science' ? 'blue' : 'stone'}>{e.type}</Chip>
                  <div className="text-[11px] text-stone-500">{e.date}</div>
                </div>
                <div className="text-[14px] text-stone-900">{e.title}</div>
                <div className="text-[12px] text-stone-500">{e.source}</div>
                <div className="mt-2 flex items-center justify-between">
                  <Confidence value={e.conf} />
                  <a className="text-[11px] text-emerald-700 inline-flex items-center gap-1 hover:underline">Open source <ExternalLink size={10} /></a>
                </div>
              </Card>
            ))}
          </div>
        </div>
        </div>
      </div>

      {site && (
        <>
          <div onClick={() => setSelected(null)} className="fixed inset-0 bg-stone-900/40 backdrop-blur-sm z-40 animate-in fade-in" />
          <aside className="fixed right-0 top-0 bottom-0 w-full md:w-[440px] z-50 bg-white shadow-2xl flex flex-col animate-in slide-in-from-right">
            {/* Hero image with risk overlay */}
            <div className="relative h-44 shrink-0 overflow-hidden">
              <ImageWithFallback
                src="https://images.unsplash.com/photo-1611843467160-25afb8df1074?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080"
                alt={site.name}
                className="w-full h-full object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-stone-950/85 via-stone-900/40 to-transparent" />
              <button onClick={() => setSelected(null)} className="absolute top-3 right-3 w-9 h-9 rounded-full bg-white/20 backdrop-blur hover:bg-white/30 text-white flex items-center justify-center"><X size={16} /></button>
              <div className="absolute bottom-4 left-5 right-5 text-white">
                <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-white/70 mb-1">EVIDENCE DRAWER</div>
                <div className="flex items-center gap-2"><MapPin size={14} /><div className="text-[18px]">{site.name}</div></div>
                <div className="text-[11px] text-white/75">{site.type} · {site.state} · {site.km} km to nearest protected area</div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              {/* Critical risk alert */}
              {site.level === 'Critical' && (
                <div className="mx-5 mt-5 p-4 rounded-xl bg-gradient-to-br from-rose-50 to-orange-50 border border-rose-200 flex gap-3">
                  <div className="w-10 h-10 rounded-full bg-rose-600 text-white flex items-center justify-center shrink-0"><Siren size={18} /></div>
                  <div>
                    <div className="text-[11px] font-mono tracking-[0.2em] uppercase text-rose-700">Critical Risk</div>
                    <div className="text-[13px] text-stone-900 mt-0.5">Tailings within 0.8 km of an ephemeral creek. Regulator notified 14 Apr 2026.</div>
                  </div>
                </div>
              )}
              <div className="px-5 pt-4 flex items-center gap-2">
                <RiskBadge level={site.level} />
                <Chip tone="stone">Buffer {site.km} km</Chip>
                <Chip tone="blue">Live monitoring</Chip>
              </div>

              {/* Overlapping features — iconified cards */}
              <div className="px-5 pt-5">
                <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-emerald-800/70 mb-2.5">Overlapping features</div>
                <div className="space-y-2">
                  {[
                    { icon: Bird, tone: 'rose', title: 'Greater Bilby habitat', sub: 'EPBC: Vulnerable · 14% decline', severity: 'High' },
                    { icon: Waves, tone: 'rose', title: 'Tailings near ephemeral creek', sub: 'Within 1 km · wet-season risk', severity: 'Critical' },
                    { icon: Droplets, tone: 'amber', title: 'Water extraction licence', sub: '2.1 GL / year · Very High stress', severity: 'Medium' },
                    { icon: Leaf, tone: 'emerald', title: 'Mulga woodland', sub: 'Adjacent · restoration pilot live', severity: 'Watch' },
                    { icon: Fish, tone: 'amber', title: 'Downstream riverine', sub: 'Turbidity flag · WA EPA', severity: 'Medium' },
                  ].map(f => {
                    const Icon = f.icon;
                    const toneMap: Record<string, string> = {
                      rose: 'bg-rose-50 text-rose-600 ring-rose-100',
                      amber: 'bg-amber-50 text-amber-700 ring-amber-100',
                      emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
                    };
                    const sevMap: Record<string, string> = {
                      Critical: 'bg-rose-600 text-white',
                      High: 'bg-rose-100 text-rose-700',
                      Medium: 'bg-amber-100 text-amber-700',
                      Watch: 'bg-emerald-100 text-emerald-700',
                    };
                    return (
                      <div key={f.title} className="flex items-center gap-3 p-3 rounded-xl border border-stone-100 hover:bg-stone-50">
                        <div className={`w-10 h-10 rounded-lg ring-1 flex items-center justify-center shrink-0 ${toneMap[f.tone]}`}><Icon size={16} /></div>
                        <div className="flex-1 min-w-0">
                          <div className="text-[13px] text-stone-900 truncate">{f.title}</div>
                          <div className="text-[11px] text-stone-500 truncate">{f.sub}</div>
                        </div>
                        <div className={`text-[10px] font-mono tracking-wider uppercase px-2 py-0.5 rounded-full ${sevMap[f.severity]}`}>{f.severity}</div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Linked evidence */}
              <div className="px-5 py-5 mt-2">
                <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-emerald-800/70 mb-2.5">Linked evidence</div>
                <div className="space-y-2">
                  {evidence.slice(0, 2).map(e => (
                    <div key={e.id} className="p-3 bg-stone-50 rounded-xl">
                      <div className="flex items-center gap-2 mb-1"><FileText size={12} className="text-stone-500" /><div className="text-[12px] text-stone-900">{e.title}</div></div>
                      <Confidence value={e.conf} />
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="shrink-0 px-5 py-4 border-t border-stone-200 bg-stone-50 flex gap-2">
              <button className="flex-1 h-9 rounded-lg border border-stone-200 bg-white hover:bg-stone-100 text-[12px] inline-flex items-center justify-center gap-1.5"><ShieldAlert size={13} /> Flag for review</button>
              <button className="flex-1 h-9 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[12px]">Add to investigation</button>
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
