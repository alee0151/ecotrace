import { useState, useRef } from 'react';
import { useNavigate } from 'react-router';
import { Barcode, Search, Building2, ArrowRight, ShieldCheck, Sparkles, Leaf, CheckCircle2, CircleDot, MapPin, TrendingUp, Flame, FileText } from 'lucide-react';
import { Card, Chip, RiskBadge, Confidence } from '../components/shared';
import { ImageWithFallback } from '../components/figma/ImageWithFallback';

const HERO_IMG = 'https://images.unsplash.com/photo-1758702160898-6f96d1db5b73?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1600';

const suggestions = [
  { label: 'Woolworths', abn: '88 000 014 675', sector: 'Retail', score: 36 },
  { label: 'BHP Group', abn: '49 004 028 077', sector: 'Mining', score: 68 },
  { label: 'Coles Group', abn: '11 004 089 936', sector: 'Retail', score: 41 },
  { label: 'Bega Cheese', abn: '81 008 358 503', sector: 'Food & Beverage', score: 54 },
];

const betterChoices = [
  { brand: 'Five:am Organics', score: 82, level: 'Low' as const, note: 'Certified regenerative dairy, low land-use footprint.' },
  { brand: 'Barambah Organics', score: 78, level: 'Low' as const, note: 'Supplier traceability to farm-gate; minimal protected area overlap.' },
  { brand: 'Pure Harvest', score: 71, level: 'Medium' as const, note: 'Plant-based alternative with 38% lower biodiversity pressure.' },
];

const TopoSvg = ({ className = '' }: { className?: string }) => (
  <svg className={className} viewBox="0 0 800 400" preserveAspectRatio="none" fill="none">
    {[0, 1, 2, 3, 4, 5, 6].map(i => (
      <path key={i} d={`M0 ${60 + i * 45} Q 200 ${20 + i * 50}, 400 ${80 + i * 40} T 800 ${50 + i * 45}`} stroke="currentColor" strokeWidth="1" opacity={0.18 - i * 0.015} />
    ))}
  </svg>
);

export function ConsumerSearch() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<'barcode' | 'brand' | 'company'>('barcode');
  const [value, setValue] = useState('');
  const [resolved, setResolved] = useState<null | {
    brand: string;
    product: string;
    parent: string;
    abn: string;
    score: number;
    source?: string;
    imageUrl?: string;
  }>(null);

  const resultsRef = useRef<HTMLDivElement>(null);

  const buildRequestBody = (
    searchMode: 'barcode' | 'brand' | 'company',
    searchValue: string
  ) => {
    if (searchMode === 'barcode') {
      return {
        barcode: searchValue,
        brand: '',
        company_or_abn: '',
      };
    }

    if (searchMode === 'brand') {
      return {
        barcode: '',
        brand: searchValue,
        company_or_abn: '',
      };
    }

    return {
      barcode: '',
      brand: '',
      company_or_abn: searchValue,
    };
  };

  const resolveWithValue = async (
    searchMode: 'barcode' | 'brand' | 'company',
    rawValue: string
  ) => {
    const searchValue = rawValue.trim();

    if (!searchValue) {
      alert('Please enter a barcode, brand, company name, or ABN.');
      return;
    }

    try {
      const requestBody = buildRequestBody(searchMode, searchValue);

      const res = await fetch('http://127.0.0.1:8000/api/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || 'Search failed');
      }

      if (!data.query_id) {
        console.error('No query_id returned', data);
        alert('Search completed, but no query_id was returned.');
        return;
      }

      localStorage.setItem('query_id', data.query_id);
      console.log('Search result:', data);

      const result = data.result;

      if (!result) {
        console.error('No result returned', data);
        alert('No matching result found.');
        return;
      }

      setResolved({
        brand:
          result.brand?.brand_name ||
          result.product?.brand ||
          result.input_value ||
          'Unknown brand',

        product:
          result.product?.product_name ||
          result.company?.legal_name ||
          result.brand?.brand_name ||
          result.input_value ||
          'Unknown product',

        parent:
          result.company?.legal_name ||
          result.legal_owner ||
          result.manufacturer ||
          result.abn_verification?.legal_name ||
          'Unknown company',

        abn:
          result.company?.abn ||
          result.abn_verification?.abn ||
          'N/A',

        score: result.confidence || 50,
        source: result.source,
        imageUrl: result.product?.image_url,
      });

      setTimeout(() => {
        resultsRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        });
      }, 100);
    } catch (err) {
      console.error(err);
      alert('Error connecting to backend');
    }
  };

  const resolve = () => {
    resolveWithValue(mode, value);
  };

  return (
    <div className="-m-0 bg-gradient-to-b from-[#f5f3ee] via-[#eef1ec] to-[#e3ebe4] min-h-[calc(100vh-65px)]">
      <section className="relative overflow-hidden">
        <div className="absolute inset-0">
          <ImageWithFallback src={HERO_IMG} alt="forest canopy" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-b from-stone-950/80 via-stone-900/70 to-[#f5f3ee]" />
          <div className="absolute inset-0 opacity-25">
            <svg className="w-full h-full" preserveAspectRatio="none">
              <defs>
                <pattern id="searchGrid" width="60" height="60" patternUnits="userSpaceOnUse">
                  <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#d6d3d1" strokeWidth="0.4" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#searchGrid)" />
            </svg>
          </div>
        </div>

        <div className="relative z-10 max-w-4xl mx-auto px-8 pt-16 pb-20">
          <div className="flex items-center gap-3 mb-5 text-emerald-200/80 font-mono text-[11px] tracking-[0.2em]">
            <span className="w-8 h-px bg-emerald-300/60" />
            <span>§ 01 · RESOLVE & SCORE</span>
          </div>

          <h1 className="text-[40px] md:text-[52px] leading-[1.05] tracking-tight text-white max-w-2xl">
            What's the real impact
            <span className="block italic text-emerald-200 font-light">of what you buy?</span>
          </h1>

          <p className="mt-5 text-stone-200/85 text-[15px] max-w-xl leading-relaxed">
            Scan a barcode, search a brand, or look up a company. We'll resolve the legal entity and score its biodiversity impact in under thirty seconds.
          </p>

          <div className="mt-9 bg-white rounded-2xl shadow-2xl p-1.5 border border-white/10">
            <div className="flex gap-1 p-1 bg-stone-50 rounded-xl">
              {([
                { id: 'barcode', label: 'Barcode', icon: Barcode },
                { id: 'brand', label: 'Brand', icon: Sparkles },
                { id: 'company', label: 'Company / ABN', icon: Building2 },
              ] as const).map(t => {
                const Icon = t.icon;
                const active = mode === t.id;

                return (
                  <button
                    key={t.id}
                    onClick={() => setMode(t.id)}
                    className={`flex-1 inline-flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-[13px] tracking-tight transition ${
                      active ? 'bg-white text-stone-900 shadow-sm' : 'text-stone-500 hover:text-stone-900'
                    }`}
                  >
                    <Icon size={14} /> {t.label}
                  </button>
                );
              })}
            </div>

            <div className="flex items-center gap-2 p-2">
              <Search size={16} className="text-stone-400 ml-2" />
              <input
                value={value}
                onChange={e => setValue(e.target.value)}
                placeholder={mode === 'barcode' ? '9 310072 011691' : mode === 'brand' ? 'e.g. Dairy Farmers, Tim Tam…' : 'Company name or ABN'}
                className="flex-1 h-11 bg-transparent outline-none text-[14px] text-stone-800 placeholder:text-stone-400"
              />
              <button
                onClick={resolve}
                className="inline-flex items-center gap-1.5 px-5 h-10 bg-emerald-500 hover:bg-emerald-400 text-stone-950 rounded-lg text-[13px] shadow-[0_8px_24px_-8px_rgba(16,185,129,0.6)]"
              >
                Analyse <ArrowRight size={14} />
              </button>
            </div>

            <div className="mx-2 mb-2 p-3 rounded-xl bg-stone-50 border border-dashed border-stone-200 group hover:bg-stone-100 hover:border-stone-300 transition-colors cursor-pointer text-center relative">
              <input type="file" accept=".pdf" className="absolute inset-0 opacity-0 cursor-pointer w-full h-full" />
              <div className="flex flex-col items-center justify-center gap-1.5 pointer-events-none">
                <div className="w-8 h-8 rounded-full bg-white shadow-sm flex items-center justify-center text-emerald-600 group-hover:scale-110 transition-transform">
                  <FileText size={14} />
                </div>
                <div className="text-[12px] font-medium text-stone-700">Upload product manual or CSR report</div>
                <div className="text-[10px] text-stone-400">PDFs only (max 10MB)</div>
              </div>
            </div>
          </div>

          <div className="mt-6 pt-5 border-t border-white/15 flex flex-wrap items-center gap-x-8 gap-y-2 text-white/80">
            <div className="font-mono text-[10px] tracking-[0.2em] text-white/50">INDEXED SOURCES</div>
            {['EPBC Act', 'ABR', 'CSIRO', 'TNFD', 'IUCN'].map(s => (
              <span key={s} className="text-[11px] tracking-tight">{s}</span>
            ))}
          </div>
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-8 py-14">
        {!resolved && (
          <div className="space-y-10">
            <div>
              <div className="flex items-end justify-between mb-5">
                <div>
                  <div className="flex items-center gap-2 text-[11px] tracking-[0.2em] uppercase text-emerald-700 font-mono mb-1">
                    <Flame size={12} /> § 02 · TRENDING
                  </div>
                  <h2 className="text-[22px] tracking-tight text-stone-900">What Australians are searching</h2>
                </div>

                <div className="hidden md:flex items-center gap-[3px] text-stone-300">
                  {Array.from({ length: 20 }).map((_, i) => (
                    <span key={i} className={`block w-px ${i % 4 === 0 ? 'h-2.5 bg-stone-400' : 'h-1.5 bg-stone-300'}`} />
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {suggestions.map((s, i) => {
                  const color = s.score >= 65 ? 'text-rose-600' : s.score >= 45 ? 'text-amber-600' : 'text-emerald-600';

                  return (
                    <button
                      key={s.label}
                      onClick={() => {
                        setMode('company');
                        setValue(s.abn);
                        resolveWithValue('company', s.abn);
                      }}
                      className="group relative p-5 bg-white border border-stone-200 hover:border-emerald-400 hover:shadow-md rounded-2xl text-left transition"
                    >
                      <div className="font-mono text-[9px] tracking-[0.2em] text-stone-400 mb-3">0{i + 1} / 04</div>
                      <div className={`text-[32px] leading-none tracking-tight ${color}`}>{s.score}</div>
                      <div className="mt-3 text-[14px] text-stone-900 truncate">{s.label}</div>
                      <div className="text-[11px] text-stone-500 mt-0.5">{s.sector}</div>
                      <div className="mt-4 pt-3 border-t border-dashed border-stone-200 flex items-center justify-between">
                        <span className="text-[10px] text-stone-400 font-mono">ABN {s.abn.slice(0, 8)}…</span>
                        <ArrowRight size={12} className="text-stone-400 group-hover:text-emerald-600 group-hover:translate-x-0.5 transition" />
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="relative grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                { icon: ShieldCheck, title: 'Verified to ABR', text: 'Every brand is resolved to a real Australian Business Registry entity.' },
                { icon: MapPin, title: 'Spatially grounded', text: 'Sites are checked against RAMSAR, EPBC and state-protected areas.' },
                { icon: Leaf, title: 'Plain English', text: 'We explain the score in three lines — no jargon, no greenwashing.' },
              ].map((f, i) => {
                const Icon = f.icon;

                return (
                  <div key={f.title} className="relative p-6 bg-white border border-stone-200 rounded-2xl overflow-hidden">
                    <TopoSvg className="absolute inset-0 w-full h-full text-emerald-800 pointer-events-none" />
                    <div className="relative">
                      <div className="font-mono text-[10px] tracking-[0.2em] text-stone-400 mb-3">0{i + 1} · {f.title.toUpperCase().split(' ')[0]}</div>
                      <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center mb-3"><Icon size={18} /></div>
                      <div className="text-[15px] text-stone-900 tracking-tight">{f.title}</div>
                      <div className="text-[12px] text-stone-600 mt-1.5 leading-relaxed">{f.text}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {resolved && (
          <div ref={resultsRef} className="space-y-6 scroll-mt-24">
            <div className="flex items-center gap-2 text-[11px] tracking-[0.2em] uppercase text-emerald-700 font-mono">
              <CheckCircle2 size={12} /> § 02 · RESOLVED
            </div>

            <Card className="p-6">
              <div className="flex items-start gap-4">
                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-emerald-100 to-blue-100 flex items-center justify-center">
                  <Leaf size={24} className="text-emerald-600" />
                </div>

                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-stone-400">Resolved entity</div>
                    <Chip tone="emerald"><CheckCircle2 size={11} /> ABR verified</Chip>
                  </div>

                  <div className="text-[18px] text-stone-900 mt-0.5 tracking-tight">{resolved.product}</div>

                  {resolved.imageUrl && (
                    <img
                      src={resolved.imageUrl}
                      alt={resolved.product}
                      className="mt-3 w-24 h-24 object-cover rounded-xl border border-stone-200"
                    />
                  )}

                  <div className="text-[13px] text-stone-600">
                    Brand <span className="text-stone-900">{resolved.brand}</span> · Owned by <span className="text-stone-900">{resolved.parent}</span> · ABN {resolved.abn}
                  </div>

                  <div className="mt-2"><Confidence value={resolved.score} /></div>
                </div>

                <button onClick={() => navigate('/app/overview')} className="inline-flex items-center gap-1.5 px-3.5 h-9 bg-stone-900 hover:bg-stone-800 text-white rounded-lg text-sm">
                  View full report <ArrowRight size={14} />
                </button>
              </div>
            </Card>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <Card className="p-6 md:col-span-1">
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-stone-400 mb-2">Biodiversity score</div>
                <div className="flex items-end gap-2">
                  <div className="text-[64px] leading-none tracking-tight text-amber-600">{resolved.score}</div>
                  <div className="text-stone-500 mb-2">/100</div>
                </div>
                <div className="mt-2"><RiskBadge level="Medium" /></div>
                <div className="mt-4 h-2 bg-stone-100 rounded-full overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-emerald-500 via-amber-400 to-rose-500" style={{ width: `${resolved.score}%` }} />
                </div>
                <div className="mt-2 flex justify-between text-[10px] text-stone-400 font-mono">
                  <span>0 · LOW</span><span>50</span><span>100 · CRITICAL</span>
                </div>
              </Card>

              <Card className="p-6 md:col-span-2">
                <div className="flex items-center gap-2 mb-3">
                  <ShieldCheck size={16} className="text-emerald-600" />
                  <div className="text-[13px] uppercase tracking-wider text-stone-500">Why this score</div>
                </div>
                <ul className="space-y-2.5">
                  <li className="flex gap-3 text-[13px] text-stone-700"><CircleDot size={14} className="text-amber-500 mt-0.5 shrink-0" />2 processing sites within 5km of RAMSAR wetlands in Victoria.</li>
                  <li className="flex gap-3 text-[13px] text-stone-700"><CircleDot size={14} className="text-emerald-500 mt-0.5 shrink-0" />Supplier chain disclosed to 3rd tier; 72% of milk from certified farms.</li>
                  <li className="flex gap-3 text-[13px] text-stone-700"><CircleDot size={14} className="text-orange-500 mt-0.5 shrink-0" />1 open EPBC referral (grazing expansion, NSW) in last 12 months.</li>
                </ul>
              </Card>
            </div>

            <div>
              <div className="flex items-end justify-between mb-4">
                <div>
                  <div className="flex items-center gap-2 text-[11px] tracking-[0.2em] uppercase text-emerald-700 font-mono mb-1">
                    <Sparkles size={12} /> § 03 · BETTER CHOICES
                  </div>
                  <h2 className="text-[22px] tracking-tight text-stone-900">Kinder to nature, in the same category</h2>
                </div>
                <TrendingUp size={16} className="text-emerald-600" />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {betterChoices.map((b, i) => (
                  <Card key={b.brand} className="p-5 hover:shadow-md transition">
                    <div className="font-mono text-[10px] tracking-[0.2em] text-stone-400 mb-2">ALT · 0{i + 1}</div>
                    <div className="flex items-center justify-between mb-2">
                      <div className="text-[14px] tracking-tight text-stone-900">{b.brand}</div>
                      <RiskBadge level={b.level} />
                    </div>
                    <div className="flex items-end gap-1 mb-2">
                      <div className="text-[32px] leading-none tracking-tight text-emerald-700">{b.score}</div>
                      <div className="text-[11px] text-stone-400 mb-1">score</div>
                    </div>
                    <div className="text-[12px] text-stone-600 leading-relaxed">{b.note}</div>
                  </Card>
                ))}
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}