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

export function SectionMono({ children }: { children: ReactNode }) {
  return (
    <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-emerald-800/70 mb-2">
      {children}
    </div>
  );
}

export type RiskLevel = "Low" | "Medium" | "High" | "Critical";

export function RiskBadge({ level, label }: { level: RiskLevel; label?: string }) {
  const map: Record<RiskLevel, string> = {
    Low: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    Medium: "bg-amber-50 text-amber-700 ring-amber-200",
    High: "bg-orange-50 text-orange-700 ring-orange-200",
    Critical: "bg-rose-50 text-rose-700 ring-rose-200",
  };
  const dot: Record<RiskLevel, string> = {
    Low: "bg-emerald-500",
    Medium: "bg-amber-500",
    High: "bg-orange-500",
    Critical: "bg-rose-500",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] ring-1 ${map[level]}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot[level]}`} />
      {label ?? `${level} Risk`}
    </span>
  );
}

export type ChipTone = "stone" | "emerald" | "blue" | "amber" | "rose" | "purple" | "sky";
export function Chip({ children, tone = "stone" }: { children: ReactNode; tone?: ChipTone }) {
  const map: Record<ChipTone, string> = {
    stone: "bg-stone-100 text-stone-700",
    emerald: "bg-emerald-50 text-emerald-700",
    blue: "bg-blue-50 text-blue-700",
    sky: "bg-sky-50 text-sky-700",
    amber: "bg-amber-50 text-amber-700",
    rose: "bg-rose-50 text-rose-700",
    purple: "bg-purple-50 text-purple-700",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] ${map[tone]}`}>
      {children}
    </span>
  );
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

export function Stat({
  label,
  value,
  delta,
  tone,
  hint,
}: {
  label: string;
  value: string;
  delta?: string;
  tone?: "up" | "down" | "flat";
  hint?: string;
}) {
  const toneClass =
    tone === "up" ? "text-emerald-600" : tone === "down" ? "text-rose-600" : "text-stone-500";
  return (
    <div className="p-5 bg-white border border-stone-200 rounded-2xl">
      <div className="text-[12px] text-stone-500">{label}</div>
      <div className="mt-1 text-[26px] text-stone-900 leading-tight">{value}</div>
      {delta && <div className={`text-[12px] mt-0.5 ${toneClass}`}>{delta}</div>}
      {hint && <div className="text-[11px] text-stone-400 mt-1">{hint}</div>}
    </div>
  );
}

export function InfoTip({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex">
      <span className="cursor-help w-3.5 h-3.5 rounded-full bg-stone-100 text-stone-500 text-[9px] flex items-center justify-center">
        i
      </span>
      <span className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-1.5 hidden w-56 -translate-x-1/2 rounded-md bg-stone-900 px-2.5 py-1.5 text-[11px] text-white group-hover:block">
        {text}
      </span>
    </span>
  );
}


