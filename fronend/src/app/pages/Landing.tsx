import React, { useState } from 'react';
import { Leaf, ArrowRight, Search, BarChart3, Shield, TrendingDown, Newspaper, ExternalLink, Users, Briefcase, CheckCircle2, Globe2, Sparkles, MapPin } from 'lucide-react';
import { ImageWithFallback } from '../components/figma/ImageWithFallback';

import { useNavigate } from 'react-router';

const HERO_IMG = 'https://images.unsplash.com/photo-1758702160898-6f96d1db5b73?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxhdXN0cmFsaWFuJTIwcmFpbmZvcmVzdCUyMGNhbm9weSUyMGJpb2RpdmVyc2l0eXxlbnwxfHx8fDE3NzcwMjk1MTV8MA&ixlib=rb-4.1.0&q=80&w=1920';
const FOREST_IMG = 'https://images.unsplash.com/photo-1771894543689-49e43c124ac1?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwyfHxhdXN0cmFsaWFuJTIwcmFpbmZvcmVzdCUyMGNhbm9weSUyMGJpb2RpdmVyc2l0eXxlbnwxfHx8fDE3NzcwMjk1MTV8MA&ixlib=rb-4.1.0&q=80&w=1080';
const MINE_IMG = 'https://images.unsplash.com/photo-1684050610978-89a6032f93d9?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwyfHxtaW5pbmclMjBpbmR1c3RyaWFsJTIwbGFuZHNjYXBlJTIwYWVyaWFsJTIwYXVzdHJhbGlhfGVufDF8fHx8MTc3NzAyOTUxOXww&ixlib=rb-4.1.0&q=80&w=1080';
const REEF_IMG = 'https://images.unsplash.com/photo-1638580591001-8c07e6f54097?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwyfHxncmVhdCUyMGJhcnJpZXIlMjByZWVmJTIwY29yYWwlMjBiaW9kaXZlcnNpdHl8ZW58MXx8fHwxNzc3MDI5NTIzfDA&ixlib=rb-4.1.0&q=80&w=1080';
const KANGAROO_IMG = 'https://images.unsplash.com/photo-1605583953063-972168057f1a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxrYW5nYXJvbyUyMGF1c3RyYWxpYW4lMjBvdXRiYWNrJTIwd2lsZGxpZmV8ZW58MXx8fHwxNzc3MDI5NTI2fDA&ixlib=rb-4.1.0&q=80&w=1080';

const stats = [
  { value: '69%', label: 'Average decline in monitored wildlife populations since 1970', source: 'WWF Living Planet Report' },
  { value: '1M+', label: 'Species threatened with extinction globally', source: 'IPBES' },
  { value: '75%', label: 'Land surface significantly altered by human activity', source: 'UN Environment' },
  { value: '$44T', label: 'Global GDP moderately or highly dependent on nature', source: 'WEF' },
];

const news = [
  {
    tag: 'Regulation',
    date: '22 Apr 2026',
    title: 'Australia finalises mandatory nature-related disclosure rules',
    source: 'Treasury',
    image: MINE_IMG,
    excerpt: 'ASX200 companies will be required to report biodiversity impacts under the new TNFD-aligned framework from FY27.',
  },
  {
    tag: 'Science',
    date: '18 Apr 2026',
    title: 'Pilbara bilby population down 14% in three years',
    source: 'CSIRO',
    image: KANGAROO_IMG,
    excerpt: 'New genomic survey links mining expansion and dingo pressure to rapid local decline of the Greater Bilby.',
  },
  {
    tag: 'Global',
    date: '11 Apr 2026',
    title: 'Great Barrier Reef hit by sixth mass bleaching event',
    source: 'AIMS',
    image: REEF_IMG,
    excerpt: 'Coral monitoring confirms widespread heat stress across 62% of surveyed reefs during the 2026 summer.',
  },
  {
    tag: 'Markets',
    date: '03 Apr 2026',
    title: 'Nature-positive funds cross AU$4.2B in AUM',
    source: 'Responsible Investment Association',
    image: FOREST_IMG,
    excerpt: 'Australian investors are rapidly reallocating toward biodiversity-aligned strategies ahead of TNFD deadlines.',
  },
];

const investorJourney = [
  { icon: Search, title: 'Search', subtitle: '01 · Input', text: 'Scan a barcode, brand, or ABN. We resolve it to a legal entity in seconds.' },
  { icon: BarChart3, title: 'Analyse', subtitle: '02 · Score', text: 'Spatial overlays, TNFD categories, and a 0–100 biodiversity risk score.' },
  { icon: Shield, title: 'Evidence', subtitle: '03 · Prove', text: 'Every claim is traced to regulatory, scientific, and independent sources.' },
  { icon: Sparkles, title: 'Act', subtitle: '04 · Decide', text: 'Find better alternatives, export a TNFD report, or set real-time alerts.' },
];

const consumerJourney = [
  { icon: Search, title: 'Search', subtitle: '01 · Scan', text: 'Scan a product barcode or search for your favorite brand.' },
  { icon: BarChart3, title: 'Analyse', subtitle: '02 · Discover', text: 'Instantly see the true environmental footprint and hidden impact.' },
  { icon: Sparkles, title: 'Act', subtitle: '03 · Choose', text: 'Find sustainable alternatives and shop with confidence.' },
];

// Industrial topographic background
const TopoSvg = ({ className = '' }: { className?: string }) => (
  <svg className={className} viewBox="0 0 800 400" preserveAspectRatio="none" fill="none">
    {[0, 1, 2, 3, 4, 5, 6].map(i => (
      <path key={i} d={`M0 ${60 + i * 45} Q 200 ${20 + i * 50}, 400 ${80 + i * 40} T 800 ${50 + i * 45}`} stroke="currentColor" strokeWidth="1" opacity={0.18 - i * 0.015} />
    ))}
  </svg>
);

const Ticks = () => (
  <div className="flex items-center gap-[3px] text-stone-300">
    {Array.from({ length: 28 }).map((_, i) => (
      <span key={i} className={`block w-px ${i % 4 === 0 ? 'h-2.5 bg-stone-400' : 'h-1.5 bg-stone-300'}`} />
    ))}
  </div>
);

export function Landing() {
  const navigate = useNavigate();
  const [activeJourney, setActiveJourney] = useState<'investor' | 'consumer'>('investor');

  const handleEnter = () => {
    navigate('/app/search');
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#f5f3ee] via-[#eef1ec] to-[#e3ebe4] text-stone-900">
      {/* Nav */}
      <div className="relative z-20 max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-gradient-to-br from-emerald-600 to-emerald-800 rounded-lg">
            <Leaf className="text-white" size={18} />
          </div>
          <div>
            <div className="text-[15px] font-semibold text-stone-900 leading-tight tracking-tight">ECOTRACE</div>
            <div className="text-[10px] text-stone-500 leading-tight tracking-[0.2em] uppercase">Biodiversity Intelligence</div>
          </div>
        </div>
        <div className="hidden md:flex items-center gap-7 text-[13px] text-stone-600">
          <a 
            href="#why-biodiversity"
            onClick={(e) => {
              e.preventDefault();
              document.getElementById('why-biodiversity')?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="hover:text-stone-900 cursor-pointer"
          >
            Why biodiversity
          </a>
          <a 
            href="#news"
            onClick={(e) => {
              e.preventDefault();
              document.getElementById('news')?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="hover:text-stone-900 cursor-pointer"
          >
            News
          </a>
          <a 
            href="#methodology"
            onClick={(e) => {
              e.preventDefault();
              document.getElementById('methodology')?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="hover:text-stone-900 cursor-pointer"
          >
            Methodology
          </a>
        </div>
        <button onClick={() => handleEnter()} className="inline-flex items-center gap-1.5 px-4 h-9 bg-stone-900 hover:bg-stone-800 text-white rounded-lg text-sm">
          Open app <ArrowRight size={14} />
        </button>
      </div>

      {/* STATS — the state of biodiversity */}
      <section id="why-biodiversity" className="relative max-w-7xl mx-auto px-6 pt-10 pb-16">
        <TopoSvg className="absolute inset-0 w-full h-full text-emerald-800 pointer-events-none opacity-50" />
        <div className="relative">
          <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
            <div>
              <div className="flex items-center gap-2 text-[11px] tracking-[0.2em] uppercase text-rose-500 mb-2 font-mono">
                <TrendingDown size={14} />
                <span>§ 01 · The state of biodiversity</span>
              </div>
              <h2 className="text-[34px] leading-tight tracking-tight text-stone-900 max-w-xl">Every claim has a consequence. We measure the fallout.</h2>
            </div>
            <div className="hidden md:block">
              <Ticks />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-px bg-stone-200 rounded-2xl overflow-hidden border border-stone-200 shadow-sm">
            {stats.map((s, i) => (
              <div key={s.label} className="bg-white/60 backdrop-blur-sm border-t md:border-t-0 md:border-l border-stone-200/50 p-7 relative hover:bg-white transition-colors">
                <div className="font-mono text-[10px] tracking-[0.2em] text-stone-400 mb-3">0{i + 1} / 04</div>
                <div className="text-[52px] leading-none text-emerald-800 tracking-tight">{s.value}</div>
                <div className="mt-3 text-[13px] text-stone-700 leading-snug font-medium">{s.label}</div>
                <div className="mt-4 pt-3 border-t border-dashed border-stone-200 text-[10px] text-stone-500 font-mono tracking-wider uppercase">Source · {s.source}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* HERO */}
      <section className="relative overflow-hidden mt-4 mx-4 md:mx-6 rounded-3xl">
        <div className="absolute inset-0">
          <ImageWithFallback src={HERO_IMG} alt="Australian forest canopy" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-b from-stone-950/70 via-stone-900/60 to-[#f5f3ee]" />
          <div className="absolute inset-0 opacity-30">
            <svg className="w-full h-full" preserveAspectRatio="none">
              <defs>
                <pattern id="heroGrid" width="80" height="80" patternUnits="userSpaceOnUse">
                  <path d="M 80 0 L 0 0 0 80" fill="none" stroke="#d6d3d1" strokeWidth="0.4" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#heroGrid)" />
            </svg>
          </div>
        </div>

        <div className="relative z-10 max-w-7xl mx-auto px-6 pt-20 pb-28 md:pt-28 md:pb-36">
          <div className="flex items-center gap-3 mb-6 text-rose-400 font-mono text-[11px] tracking-[0.2em] uppercase">
            <span className="w-8 h-px bg-rose-500/60" />
            <span>We're losing nature faster than we can measure it.</span>
          </div>
          <h1 className="text-[44px] md:text-[60px] leading-[1.05] tracking-tight text-white max-w-4xl">
            Knowing your everyday store impact
            <span className="block italic text-emerald-300 font-light">on nature and the environment.</span>
          </h1>
          <p className="mt-6 text-stone-200/90 text-[16px] max-w-xl leading-relaxed">
            EcoTrace fuses regulatory filings, scientific data, and supply-chain records into a trusted biodiversity risk score. Stop guessing—start tracing the footprint of what you buy and who you back.
          </p>

          <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 gap-5 max-w-3xl">
            <div className="bg-stone-900/40 backdrop-blur-md border border-white/10 p-6 rounded-2xl flex flex-col justify-between group hover:bg-stone-900/60 transition">
              <div>
                <div className="flex items-center gap-2 text-emerald-400 mb-3">
                  <Briefcase size={18} />
                  <span className="font-mono text-[11px] tracking-[0.15em] uppercase">For Investors</span>
                </div>
                <h3 className="text-white text-[18px] md:text-[20px] leading-snug tracking-tight mb-2">
                  Do you understand the true environmental impact of your portfolio?
                </h3>
                <p className="text-stone-300 text-[14px] leading-relaxed">
                  Identify hidden biodiversity risks and protect nature before you invest in companies that degrade it.
                </p>
              </div>
              <button onClick={() => navigate('/app/watchlist')} className="mt-6 w-full inline-flex items-center justify-center gap-2 px-4 h-11 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-stone-950 text-[14px] font-medium shadow-[0_8px_24px_-8px_rgba(16,185,129,0.5)] transition-colors">
                Explore Investor Tools <ArrowRight size={15} />
              </button>
            </div>

            <div className="bg-white/5 backdrop-blur-md border border-white/10 p-6 rounded-2xl flex flex-col justify-between group hover:bg-white/10 transition">
              <div>
                <div className="flex items-center gap-2 text-blue-300 mb-3">
                  <Users size={18} />
                  <span className="font-mono text-[11px] tracking-[0.15em] uppercase">For Consumers</span>
                </div>
                <h3 className="text-white text-[18px] md:text-[20px] leading-snug tracking-tight mb-2">
                  Do you know what your favorite products are really made from?
                </h3>
                <p className="text-stone-300 text-[14px] leading-relaxed">
                  Scan the everyday items you buy to uncover their hidden footprint on ecosystems.
                </p>
              </div>
              <button onClick={() => navigate('/app/search')} className="mt-6 w-full inline-flex items-center justify-center gap-2 px-4 h-11 rounded-xl bg-white/10 hover:bg-white/20 text-white text-[14px] font-medium border border-white/20 transition-colors">
                Trace Consumer Impact <ArrowRight size={15} />
              </button>
            </div>
          </div>
          
          {/* Industrial measurement strip */}
          <div className="mt-14 pt-6 border-t border-white/15 flex flex-wrap items-center gap-x-10 gap-y-3 text-white/80">
            <div className="font-mono text-[10px] tracking-[0.2em] text-white/50">INDEXED SOURCES</div>
            {['EPBC Act', 'CSIRO', 'IPBES', 'TNFD', 'IUCN', 'ABR', 'WA EPA'].map(s => (
              <span key={s} className="text-[12px] tracking-tight">{s}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Split feature — industrial + environment */}
      <section className="max-w-7xl mx-auto px-6 pb-24">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="relative rounded-2xl overflow-hidden aspect-[4/3] md:aspect-auto md:h-[320px]">
            <ImageWithFallback src={MINE_IMG} alt="industrial landscape" className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-stone-950/80 via-stone-900/30 to-transparent" />
            <div className="absolute inset-0 p-6 flex flex-col justify-between text-white">
              <div className="font-mono text-[10px] tracking-[0.2em] text-white/70">SECTOR · EXTRACTIVE</div>
              <div>
                <div className="text-[22px] leading-tight">The industrial footprint</div>
                <div className="text-[12px] text-white/75 max-w-xs mt-1">From the Pilbara to the Hunter — we map operational sites, tailings, and their overlap with protected areas.</div>
              </div>
            </div>
          </div>
          <div className="relative rounded-2xl overflow-hidden aspect-[4/3] md:aspect-auto md:h-[320px]">
            <ImageWithFallback src={FOREST_IMG} alt="rainforest path" className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-emerald-950/85 via-emerald-900/30 to-transparent" />
            <div className="absolute inset-0 p-6 flex flex-col justify-between text-white">
              <div className="font-mono text-[10px] tracking-[0.2em] text-emerald-200">SECTOR · ECOSYSTEM</div>
              <div>
                <div className="text-[22px] leading-tight">The living baseline</div>
                <div className="text-[12px] text-white/80 max-w-xs mt-1">Species distributions, RAMSAR wetlands, and threatened habitats — the counterweight to every industrial claim.</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* USER JOURNEY — aesthetic, connected */}
      <section id="methodology" className="relative bg-stone-950 text-stone-100 overflow-hidden">
        <div className="absolute inset-0 opacity-[0.15]">
          <TopoSvg className="w-full h-full text-emerald-300" />
        </div>
        <div className="absolute inset-0 opacity-40">
          <svg className="w-full h-full" preserveAspectRatio="none">
            <defs>
              <pattern id="darkGrid" width="60" height="60" patternUnits="userSpaceOnUse">
                <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#1c1917" strokeWidth="1" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#darkGrid)" />
          </svg>
        </div>

        <div className="relative max-w-7xl mx-auto px-6 py-24">
          <div className="text-center mb-14">
            <div className="inline-flex items-center gap-3 text-[11px] tracking-[0.25em] uppercase text-emerald-300/80 font-mono mb-5">
              <span className="w-8 h-px bg-emerald-400/60" />
              § 02 · How it works
              <span className="w-8 h-px bg-emerald-400/60" />
            </div>
            <h2 className="text-[40px] md:text-[48px] tracking-tight leading-[1.05] text-white">
              A simple, <span className="italic text-emerald-300 font-light">transparent</span> journey.
            </h2>
            <p className="mt-4 text-stone-300/80 text-[15px] max-w-xl mx-auto mb-10">From question to evidence — tailored whether you're managing AU$4B in assets or buying everyday groceries.</p>

            <div className="flex justify-center">
              <div className="inline-flex items-center p-1 rounded-2xl bg-white/[0.03] border border-white/10 backdrop-blur-sm shadow-inner">
                <button 
                  onClick={() => setActiveJourney('investor')}
                  className={`flex items-center gap-2.5 px-6 py-3 rounded-xl text-[14px] font-medium transition-all duration-300 ${
                    activeJourney === 'investor' 
                      ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20 shadow-sm' 
                      : 'text-stone-400 hover:text-stone-200 hover:bg-white/[0.05] border border-transparent'
                  }`}
                >
                  <Briefcase size={16} />
                  If you want to invest to company
                </button>
                <button 
                  onClick={() => setActiveJourney('consumer')}
                  className={`flex items-center gap-2.5 px-6 py-3 rounded-xl text-[14px] font-medium transition-all duration-300 ${
                    activeJourney === 'consumer' 
                      ? 'bg-blue-500/15 text-blue-300 border border-blue-500/20 shadow-sm' 
                      : 'text-stone-400 hover:text-stone-200 hover:bg-white/[0.05] border border-transparent'
                  }`}
                >
                  <Users size={16} />
                  If you want to see your product impact
                </button>
              </div>
            </div>
          </div>

          <div className="relative min-h-[320px]">
            {/* Investor Journey */}
            {activeJourney === 'investor' && (
              <div className="relative transition-opacity duration-500 opacity-100">
                <svg className="hidden md:block absolute inset-x-0 top-12 h-4 w-full" preserveAspectRatio="none" viewBox="0 0 1000 20">
                  <line x1="60" y1="10" x2="940" y2="10" stroke="#10b981" strokeWidth="1" strokeDasharray="6 8" opacity="0.55" />
                  {[125, 375, 625, 875].map((cx, i) => (
                    <g key={i}>
                      <circle cx={cx} cy="10" r="6" fill="#10b981" opacity="0.2" />
                      <circle cx={cx} cy="10" r="2.5" fill="#10b981" />
                    </g>
                  ))}
                </svg>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-6 md:gap-5 relative">
                  {investorJourney.map((j, i) => {
                    const Icon = j.icon;
                    return (
                      <div key={j.title} className="relative">
                        <div className="flex items-center gap-3 mb-5">
                          <div className="w-12 h-12 rounded-full border border-emerald-400/40 bg-stone-950 flex items-center justify-center text-emerald-300 relative z-10">
                            <span className="text-[15px] tracking-tight">0{i + 1}</span>
                          </div>
                          <div className="flex-1 h-px bg-gradient-to-r from-emerald-400/40 to-transparent" />
                        </div>
                        <div className="p-6 rounded-2xl bg-white/[0.04] border border-white/10 backdrop-blur-sm hover:bg-white/[0.06] transition h-full">
                          <div className="flex items-center gap-2 mb-4">
                            <div className="w-9 h-9 rounded-lg bg-emerald-400/15 text-emerald-300 flex items-center justify-center">
                              <Icon size={16} />
                            </div>
                            <div className="font-mono text-[10px] tracking-[0.2em] text-stone-400">{j.subtitle}</div>
                          </div>
                          <div className="text-[19px] tracking-tight text-white mb-1.5">{j.title}</div>
                          <div className="text-[13px] text-stone-400 leading-relaxed">{j.text}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Consumer Journey */}
            {activeJourney === 'consumer' && (
              <div className="relative transition-opacity duration-500 opacity-100">
                <svg className="hidden md:block absolute inset-x-0 top-12 h-4 w-full" preserveAspectRatio="none" viewBox="0 0 1000 20">
                  <line x1="60" y1="10" x2="940" y2="10" stroke="#93c5fd" strokeWidth="1" strokeDasharray="6 8" opacity="0.4" />
                  {[166, 500, 833].map((cx, i) => (
                    <g key={i}>
                      <circle cx={cx} cy="10" r="6" fill="#93c5fd" opacity="0.2" />
                      <circle cx={cx} cy="10" r="2.5" fill="#93c5fd" />
                    </g>
                  ))}
                </svg>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8 relative">
                  {consumerJourney.map((j, i) => {
                    const Icon = j.icon;
                    return (
                      <div key={j.title} className="relative">
                        <div className="flex items-center gap-3 mb-5">
                          <div className="w-12 h-12 rounded-full border border-blue-400/40 bg-stone-950 flex items-center justify-center text-blue-300 relative z-10">
                            <span className="text-[15px] tracking-tight">0{i + 1}</span>
                          </div>
                          <div className="flex-1 h-px bg-gradient-to-r from-blue-400/40 to-transparent" />
                        </div>
                        <div className="p-6 rounded-2xl bg-white/[0.04] border border-white/10 backdrop-blur-sm hover:bg-white/[0.06] transition h-full">
                          <div className="flex items-center gap-2 mb-4">
                            <div className="w-9 h-9 rounded-lg bg-blue-400/15 text-blue-300 flex items-center justify-center">
                              <Icon size={16} />
                            </div>
                            <div className="font-mono text-[10px] tracking-[0.2em] text-stone-400">{j.subtitle}</div>
                          </div>
                          <div className="text-[19px] tracking-tight text-white mb-1.5">{j.title}</div>
                          <div className="text-[13px] text-stone-400 leading-relaxed">{j.text}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* NEWS */}
      <section id="news" className="max-w-7xl mx-auto px-6 py-24">
        <div className="flex items-end justify-between mb-10">
          <div>
            <div className="flex items-center gap-2 text-[11px] tracking-[0.2em] uppercase text-emerald-700 mb-2 font-mono">
              <Newspaper size={13} />
              <span>§ 03 · Biodiversity newsroom</span>
            </div>
            <h2 className="text-[34px] tracking-tight text-stone-900 leading-tight">Updates from Australia & beyond</h2>
          </div>
          <a className="inline-flex items-center gap-1 text-[13px] text-emerald-700 hover:underline cursor-pointer">Full newsroom <ExternalLink size={12} /></a>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {news.map((n, i) => (
            <article key={n.title} className={`group bg-white border border-stone-200 rounded-2xl overflow-hidden hover:shadow-lg transition ${i === 0 ? 'md:col-span-2 md:flex' : ''}`}>
              <div className={`${i === 0 ? 'md:w-1/2' : ''} aspect-[16/9] md:aspect-auto overflow-hidden ${i === 0 ? 'md:min-h-[280px]' : 'h-48'}`}>
                <ImageWithFallback src={n.image} alt={n.title} className="w-full h-full object-cover group-hover:scale-105 transition duration-700" />
              </div>
              <div className={`p-6 flex flex-col ${i === 0 ? 'md:w-1/2 md:p-8 md:justify-center' : ''}`}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[10px] tracking-[0.15em] uppercase font-mono">{n.tag}</span>
                  <span className="text-[11px] text-stone-400 font-mono tracking-wider">{n.date} · {n.source}</span>
                </div>
                <h3 className={`${i === 0 ? 'text-[24px]' : 'text-[17px]'} text-stone-900 leading-snug mb-2 tracking-tight`}>{n.title}</h3>
                <p className="text-[13px] text-stone-600 leading-relaxed">{n.excerpt}</p>
                <a className="mt-4 inline-flex items-center gap-1 text-[12px] text-emerald-700 hover:gap-2 transition-all cursor-pointer">Read more <ArrowRight size={12} /></a>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* FOOTER */}
      <footer className="border-t border-stone-200 bg-[#ede9e2]">
        <div className="max-w-7xl mx-auto px-6 py-10 grid grid-cols-1 md:grid-cols-4 gap-6 text-[13px] text-stone-600">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <div className="p-1.5 bg-emerald-700 rounded-md"><Leaf size={14} className="text-white" /></div>
              <div className="text-stone-900 tracking-tight">EcoTrace</div>
            </div>
            <div className="text-[12px] text-stone-500 leading-relaxed">Biodiversity risk intelligence for the TNFD era. Built in Australia.</div>
            <div className="mt-3 font-mono text-[10px] tracking-[0.2em] text-stone-400 inline-flex items-center gap-1"><MapPin size={11} /> MELBOURNE · VIC · AU</div>
          </div>
          <div>
            <div className="text-stone-900 mb-3">Platform</div>
            <ul className="space-y-1.5 text-[12px]"><li>Consumer search</li><li>Supply chain</li><li>Knowledge graph</li></ul>
          </div>
          <div>
            <div className="text-stone-900 mb-3">Resources</div>
            <ul className="space-y-1.5 text-[12px]"><li>Methodology</li><li>TNFD alignment</li><li>Data sources</li><li>API docs</li></ul>
          </div>
          <div>
            <div className="text-stone-900 mb-3">Company</div>
            <ul className="space-y-1.5 text-[12px]"><li>About</li><li>Careers</li><li>Press</li><li>Contact</li></ul>
          </div>
        </div>
        <div className="border-t border-stone-200">
          <div className="max-w-7xl mx-auto px-6 py-4 flex flex-col md:flex-row items-center justify-between gap-3 text-[11px] text-stone-500 font-mono tracking-wider">
            <div>© 2026 ECOTRACE · ALL RIGHTS RESERVED</div>
            <div className="flex gap-5"><a>PRIVACY</a><a>TERMS</a><a>SECURITY</a></div>
          </div>
        </div>
      </footer>
    </div>
  );
}
