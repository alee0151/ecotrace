import { ReactNode } from 'react';

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-white border border-stone-200 rounded-2xl shadow-sm ${className}`}>
      {children}
    </div>
  );
}

export function SectionTitle({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div className="text-[13px] uppercase tracking-wider text-stone-500">{title}</div>
      {action}
    </div>
  );
}

export function RiskBadge({ level }: { level: 'Low' | 'Medium' | 'High' | 'Critical' }) {
  const map: Record<string, string> = {
    Low: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    Medium: 'bg-amber-50 text-amber-700 ring-amber-200',
    High: 'bg-orange-50 text-orange-700 ring-orange-200',
    Critical: 'bg-rose-50 text-rose-700 ring-rose-200',
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] ring-1 ${map[level]}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${
        level === 'Low' ? 'bg-emerald-500'
          : level === 'Medium' ? 'bg-amber-500'
          : level === 'High' ? 'bg-orange-500'
          : 'bg-rose-500'
      }`} />
      {level} Risk
    </span>
  );
}

export function Chip({ children, tone = 'stone' }: { children: ReactNode; tone?: 'stone' | 'emerald' | 'blue' | 'amber' | 'rose' | 'purple' }) {
  const map = {
    stone: 'bg-stone-100 text-stone-700',
    emerald: 'bg-emerald-50 text-emerald-700',
    blue: 'bg-blue-50 text-blue-700',
    amber: 'bg-amber-50 text-amber-700',
    rose: 'bg-rose-50 text-rose-700',
    purple: 'bg-purple-50 text-purple-700',
  };
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] ${map[tone]}`}>{children}</span>;
}

export function Confidence({ value }: { value: number }) {
  const tone = value >= 85 ? 'emerald' : value >= 70 ? 'blue' : 'amber';
  const bar = tone === 'emerald' ? 'bg-emerald-500' : tone === 'blue' ? 'bg-blue-500' : 'bg-amber-500';
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-stone-100 rounded-full overflow-hidden">
        <div className={`h-full ${bar}`} style={{ width: `${value}%` }} />
      </div>
      <span className="text-[11px] text-stone-500">{value}% confidence <span className="text-stone-400">· AI-assessed source reliability</span></span>
    </div>
  );
}

export function Stat({ label, value, delta, tone }: { label: string; value: string; delta?: string; tone?: 'up' | 'down' | 'flat' }) {
  const toneClass = tone === 'up' ? 'text-emerald-600' : tone === 'down' ? 'text-rose-600' : 'text-stone-500';
  return (
    <div className="p-5 bg-white border border-stone-200 rounded-2xl">
      <div className="text-[12px] text-stone-500">{label}</div>
      <div className="mt-1 text-[26px] text-stone-900">{value}</div>
      {delta && <div className={`text-[12px] mt-0.5 ${toneClass}`}>{delta}</div>}
    </div>
  );
}
