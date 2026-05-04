import { useState } from "react";
import { Building2, ChevronDown, FileText, MapPin, Newspaper } from "lucide-react";
import { Chip } from "./shared";

export type SpatialSite = {
  id: string;
  name: string;
  lat: number;
  lon: number;
  radiusKm: number;
  company: string;
  ticker: string;
  sector: string;
  abn: string;
  locationMethod?: string;
  locationConfidence?: string;
  sourceTags?: Array<{ label: string; tone: "emerald" | "blue" | "amber" }>;
};

export const spatialSites: SpatialSite[] = [
  {
    id: "olympicdam",
    name: "Olympic Dam — SA",
    lat: -30.4419,
    lon: 136.8812,
    radiusKm: 10,
    company: "BHP Group",
    ticker: "ASX:BHP",
    sector: "Materials · Mining",
    abn: "49 004 028 077",
  },
  {
    id: "pilbara",
    name: "Pilbara WAIO — WA",
    lat: -22.6,
    lon: 117.78,
    radiusKm: 10,
    company: "BHP Group",
    ticker: "ASX:BHP",
    sector: "Materials · Mining",
    abn: "49 004 028 077",
  },
  {
    id: "queensland",
    name: "Mt Arthur Coal — NSW",
    lat: -32.36,
    lon: 150.95,
    radiusKm: 10,
    company: "BHP Group",
    ticker: "ASX:BHP",
    sector: "Materials · Mining",
    abn: "49 004 028 077",
  },
];

function formatCoords(site: SpatialSite) {
  return `${site.lat.toFixed(2)}, ${site.lon.toFixed(2)}`;
}

export function SpatialContextBar({
  site,
  sites = spatialSites,
  onSiteChange,
}: {
  site: SpatialSite;
  sites?: SpatialSite[];
  onSiteChange: (site: SpatialSite) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-6">
      <div className="flex items-center gap-4">
        <div className="flex size-12 items-center justify-center rounded-xl bg-white border border-stone-200 shadow-sm">
          <Building2 className="size-6 text-stone-500" />
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-stone-400">
            Portfolio › {site.company}
          </div>
          <div className="flex items-baseline gap-3">
            <h1 className="text-[26px] text-stone-900 leading-tight">{site.company}</h1>
            <Chip tone="stone">{site.ticker}</Chip>
            <span className="text-[12px] text-stone-500">{site.sector}</span>
          </div>
          <div className="text-[12px] text-emerald-700 mt-0.5">
            Biodiversity Spatial Analysis · ABN {site.abn}
            {site.locationConfidence ? ` · ${site.locationConfidence} confidence` : ""}
          </div>
        </div>
      </div>

      <div className="flex flex-col items-end gap-2">
        <div className="relative">
          <button
            onClick={() => setOpen(!open)}
            className="flex min-w-[300px] items-center justify-between gap-3 rounded-xl bg-white border border-stone-200 px-3.5 py-2.5 text-left shadow-sm hover:border-emerald-300"
          >
            <span className="flex items-center gap-2.5">
              <MapPin className="size-4 text-emerald-600" />
              <span>
                <span className="block text-[10px] tracking-wider text-stone-400 uppercase">
                  Active Site
                </span>
                <span className="block text-[14px] text-stone-900">{site.name}</span>
              </span>
            </span>
            <span className="flex items-center gap-2">
              <span className="text-[10px] text-stone-400 font-mono">
                {formatCoords(site)} · {site.radiusKm} km
              </span>
              <ChevronDown
                className={`size-4 text-stone-400 transition ${open ? "rotate-180" : ""}`}
              />
            </span>
          </button>
          {open && (
            <div className="absolute right-0 z-30 mt-1.5 w-[340px] overflow-hidden rounded-xl bg-white border border-stone-200 shadow-lg">
              <div className="border-b border-stone-100 px-3 py-2 text-[10px] tracking-wider text-stone-400 uppercase">
                {sites.length} mapped sites
              </div>
              {sites.map((s) => (
                <button
                  key={s.id}
                  onClick={() => {
                    onSiteChange(s);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center justify-between px-3 py-2.5 text-left text-[12px] hover:bg-stone-50 ${
                    s.id === site.id ? "bg-emerald-50 text-emerald-700" : "text-stone-800"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <MapPin className="size-3.5 text-stone-400" />
                    {s.name}
                  </span>
                  <span className="text-[10px] text-stone-400 font-mono">{formatCoords(s)}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          {(site.sourceTags ?? [
            { label: "Source: ABN Registration", tone: "emerald" as const },
            { label: site.locationMethod ? `Inference: ${site.locationMethod}` : "Inference: postcode centroid", tone: "blue" as const },
            { label: "Layer A: ALA + IUCN", tone: "amber" as const },
          ]).map((tag) => (
            <SourceTag
              key={tag.label}
              icon={tag.label.includes("Layer") ? Newspaper : FileText}
              label={tag.label}
              tone={tag.tone}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function SourceTag({
  icon: Icon,
  label,
  tone,
}: {
  icon: any;
  label: string;
  tone: "emerald" | "blue" | "amber";
}) {
  const tones = {
    emerald: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    blue: "bg-blue-50 text-blue-700 ring-blue-200",
    amber: "bg-amber-50 text-amber-700 ring-amber-200",
  } as const;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] ring-1 ${tones[tone]}`}
    >
      <Icon className="size-3" />
      {label}
    </span>
  );
}
