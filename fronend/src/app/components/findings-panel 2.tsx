import {
  ShieldAlert,
  ShieldCheck,
  TreePine,
  Bird,
  AlertTriangle,
  ExternalLink,
  MapPinned,
  Scale,
  Globe2,
} from "lucide-react";
import { Card, Chip, InfoTip, RiskBadge, SectionMono } from "./shared";

const iucnCategories = [
  { code: "CR", label: "Critically Endangered", count: 7, bar: "bg-rose-500", text: "text-rose-700" },
  { code: "EN", label: "Endangered", count: 14, bar: "bg-orange-500", text: "text-orange-700" },
  { code: "VU", label: "Vulnerable", count: 23, bar: "bg-amber-400", text: "text-amber-700" },
  { code: "NT", label: "Near Threatened", count: 41, bar: "bg-sky-400", text: "text-sky-700" },
  { code: "LC", label: "Least Concern", count: 1160, bar: "bg-emerald-500", text: "text-emerald-700" },
];

const max = Math.max(...iucnCategories.map((c) => c.count));

function PanelHeader({ icon: Icon, title, subtitle }: { icon: any; title: string; subtitle?: string }) {
  return (
    <div className="mb-3 flex items-center gap-2.5">
      <div className="flex size-8 items-center justify-center rounded-lg bg-emerald-50 ring-1 ring-emerald-200">
        <Icon className="size-4 text-emerald-700" />
      </div>
      <div>
        <div className="text-[14px] text-stone-900">{title}</div>
        {subtitle && <div className="text-[11px] text-stone-500">{subtitle}</div>}
      </div>
    </div>
  );
}

export function FindingsPanel() {
  return (
    <div className="h-full overflow-y-auto pr-2">
      {/* Section A */}
      <div className="mb-2 flex items-center justify-between">
        <SectionMono>Layer A · Species & Threats</SectionMono>
        <span className="text-[10px] text-stone-400 font-mono">UPDATED 2 MIN AGO</span>
      </div>
      <PanelHeader icon={Bird} title="Species & Threat Inventory" subtitle="Who lives here & what's at risk" />

      <Card className="p-5 mb-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-1.5 text-[12px] text-stone-500">
              Total Species Recorded
              <InfoTip text="Filtered for ALA quality profile · vetted occurrences only" />
            </div>
            <div className="mt-1 text-[32px] leading-tight tracking-tight text-stone-900">1,245</div>
            <div className="mt-1 text-[11px] text-stone-500">
              Sourced via ALA Biocache · 10 km radius
            </div>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <Chip tone="emerald">+3.2% w/w</Chip>
            <span className="text-[10px] text-stone-400">42,108 records</span>
          </div>
        </div>
      </Card>

      <Card className="p-5 mb-6">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[12px] uppercase tracking-wider text-stone-500">
            IUCN Red List Breakdown
          </div>
          <InfoTip text="Weighted risk signal aggregated from IUCN Red List API" />
        </div>
        <div className="space-y-2.5">
          {iucnCategories.map((c) => (
            <div key={c.code} className="grid grid-cols-[28px_1fr_56px] items-center gap-2.5">
              <span className={`rounded px-1.5 py-0.5 text-center text-[10px] tracking-wider text-white ${c.bar}`}>
                {c.code}
              </span>
              <div className="relative h-5 overflow-hidden rounded bg-stone-100">
                <div className={`h-full ${c.bar} opacity-90`} style={{ width: `${(c.count / max) * 100}%` }} />
                <span className="absolute inset-0 flex items-center px-2 text-[10px] text-stone-700">
                  {c.label}
                </span>
              </div>
              <span className={`text-right text-[12px] tabular-nums ${c.text}`}>{c.count}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Section B */}
      <div className="mb-2 flex items-center justify-between">
        <SectionMono>Layer B · Habitat & Liability</SectionMono>
        <span className="text-[10px] text-stone-400 font-mono">EPBC v2024.3</span>
      </div>
      <PanelHeader
        icon={TreePine}
        title="Habitat Sensitivity & Legal Liability"
        subtitle="Protected areas & regulatory exposure"
      />

      <Card className="p-4 mb-3 ring-1 ring-rose-200">
        <div className="flex items-start gap-3">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-rose-50 ring-1 ring-rose-200">
            <ShieldAlert className="size-4 text-rose-600" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <Chip tone="rose">CAPAD</Chip>
              <span className="text-[12px] text-stone-500">Protected Areas</span>
              <RiskBadge level="High" label="Overlap" />
            </div>
            <div className="mt-1.5 text-[13px] text-stone-900">
              High-Risk Multiplier: Overlaps Indigenous Protected Area
            </div>
            <div className="mt-0.5 text-[11px] text-stone-500">
              Arabana IPA · 1,224 km² · Buffer breach 2.3 km
            </div>
          </div>
        </div>
      </Card>

      <Card className="p-4 mb-3">
        <div className="flex items-start gap-3">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-sky-50 ring-1 ring-sky-200">
            <Globe2 className="size-4 text-sky-600" />
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-stone-500">IBRA Bioregion</span>
              <Chip tone="amber">Endemism: High</Chip>
            </div>
            <div className="mt-1 text-[13px] text-stone-900">Stony Plains (STP)</div>
            <div className="mt-0.5 text-[11px] text-stone-500">
              Subregion: Breakaways · Arid acacia shrublands
            </div>
          </div>
        </div>
      </Card>

      <Card className="p-4 mb-3">
        <div className="flex items-start gap-3">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-amber-50 ring-1 ring-amber-200">
            <MapPinned className="size-4 text-amber-600" />
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-stone-500">Key Biodiversity Area (KBA)</span>
              <Chip tone="amber">Adjacent · 4.1 km</Chip>
            </div>
            <div className="mt-1 text-[13px] text-stone-900">Lake Eyre Basin KBA</div>
            <div className="mt-0.5 text-[11px] text-stone-500">
              Globally significant for waterbird breeding events
            </div>
          </div>
        </div>
      </Card>

      <Card className="p-4 mb-3 ring-2 ring-rose-300 shadow-[0_8px_30px_-12px_rgba(244,63,94,0.35)]">
        <div className="flex items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-rose-50 ring-2 ring-rose-200">
            <Scale className="size-4 text-rose-600" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <Chip tone="rose">EPBC Act</Chip>
              <span className="text-[12px] text-rose-700">Regulatory Liability</span>
              <AlertTriangle className="ml-auto size-4 text-rose-500" />
            </div>
            <div className="mt-2 text-[13px] text-stone-900">
              Overlaps modeled habitat for{" "}
              <span className="text-rose-700">12 listed species</span>
            </div>
            <div className="mt-1 text-[11px] text-stone-500">
              DCCEEW SNES · 4 migratory · 3 critically endangered · Referral likely required
            </div>
            <div className="mt-3 flex items-center gap-2">
              <button className="inline-flex items-center gap-1.5 rounded-lg bg-rose-50 px-2.5 py-1.5 text-[12px] text-rose-700 ring-1 ring-rose-200 hover:bg-rose-100">
                View Intersecting Species
                <ExternalLink className="size-3" />
              </button>
              <button className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] text-stone-500 hover:text-stone-800">
                Generate Referral Brief
              </button>
            </div>
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <div className="flex items-center gap-2 text-[12px] text-stone-500">
          <ShieldCheck className="size-4 text-emerald-600" />
          Composite Site Risk Score
          <InfoTip text="Weighted blend of IUCN, CAPAD, KBA, and SNES signals" />
        </div>
        <div className="mt-2 flex items-end justify-between">
          <div>
            <div className="text-[28px] tracking-tight text-rose-700 leading-tight">
              82<span className="text-[14px] text-stone-400">/100</span>
            </div>
            <div className="text-[11px] text-rose-700/80">Tier 1 — Critical</div>
          </div>
          <div className="h-2.5 w-40 overflow-hidden rounded-full bg-stone-100">
            <div className="h-full w-[82%] bg-gradient-to-r from-emerald-500 via-amber-400 to-rose-500" />
          </div>
        </div>
      </Card>
    </div>
  );
}
