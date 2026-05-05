import {
  AlertTriangle,
  Bird,
  Database,
  ExternalLink,
  MapPinned,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import type { SpatialLayerAResponse, SpatialSpeciesRecord } from "../../lib/api";
import { Card, Chip, InfoTip, RiskBadge, SectionMono } from "./shared";

const categoryStyles: Record<string, { bar: string; text: string; tone: "rose" | "amber" | "emerald" | "sky" | "stone" }> = {
  CR: { bar: "bg-rose-600", text: "text-rose-700", tone: "rose" },
  EN: { bar: "bg-orange-500", text: "text-orange-700", tone: "rose" },
  VU: { bar: "bg-amber-400", text: "text-amber-700", tone: "amber" },
  NT: { bar: "bg-sky-400", text: "text-sky-700", tone: "sky" },
  LC: { bar: "bg-emerald-500", text: "text-emerald-700", tone: "emerald" },
  DD: { bar: "bg-stone-400", text: "text-stone-700", tone: "stone" },
  EX: { bar: "bg-stone-700", text: "text-stone-700", tone: "stone" },
  EW: { bar: "bg-stone-700", text: "text-stone-700", tone: "stone" },
};

function categoryCode(label: string) {
  return label.split(" ")[0];
}

function riskLevel(score: number) {
  if (score >= 80) return "Critical";
  if (score >= 60) return "High";
  if (score >= 35) return "Medium";
  return "Low";
}

function formatNumber(value?: number) {
  return new Intl.NumberFormat("en-AU").format(value ?? 0);
}

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

function EmptyRow({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-stone-200 bg-stone-50 px-3 py-2 text-[12px] text-stone-500">
      {label}
    </div>
  );
}

function SpeciesRow({ species }: { species: SpatialSpeciesRecord }) {
  const code = species.iucn_category ?? "NA";
  const style = categoryStyles[code] ?? categoryStyles.DD;

  return (
    <div className="rounded-lg border border-stone-200 bg-white px-3 py-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-[13px] text-stone-900">{species.scientific_name}</div>
          <div className="mt-0.5 truncate text-[11px] text-stone-500">
            {species.common_name || "Common name unavailable"} | {formatNumber(species.record_count)} records
          </div>
        </div>
        <Chip tone={style.tone}>{code}</Chip>
      </div>
      {species.iucn_url && (
        <a
          href={species.iucn_url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-[11px] text-emerald-700 hover:text-emerald-800"
        >
          IUCN record
          <ExternalLink className="size-3" />
        </a>
      )}
    </div>
  );
}

export function FindingsPanel({
  layerA,
  loading,
  error,
  onRetry,
}: {
  layerA?: SpatialLayerAResponse | null;
  loading?: boolean;
  error?: string | null;
  onRetry: () => void;
}) {
  const score = layerA?.species_threat_score ?? 0;
  const breakdown = Object.entries(layerA?.score_breakdown ?? {});
  const threatenedSpecies = layerA?.threatened_species ?? [];
  const allSpecies = layerA?.all_species ?? [];
  const maxBreakdown = Math.max(1, ...breakdown.map(([, count]) => count));
  const generatedAt = layerA?.generated_at
    ? new Date(layerA.generated_at).toLocaleString("en-AU", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Waiting for backend";

  return (
    <div className="h-full overflow-y-auto pr-2">
      <div className="mb-2 flex items-center justify-between">
        <SectionMono>Layer A | Species & Threats</SectionMono>
        <button
          onClick={onRetry}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] text-stone-500 hover:bg-stone-100 disabled:opacity-50"
        >
          <RefreshCw className={`size-3 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      <PanelHeader
        icon={Bird}
        title="Species & Threat Inventory"
        subtitle="ALA Biocache occurrence query enriched with IUCN Red List data"
      />

      {error && (
        <Card className="mb-3 p-4 ring-1 ring-rose-200">
          <div className="flex items-start gap-3">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-rose-50">
              <AlertTriangle className="size-4 text-rose-600" />
            </div>
            <div>
              <div className="text-[13px] text-stone-900">Layer A request failed</div>
              <div className="mt-1 text-[11px] leading-relaxed text-stone-500">{error}</div>
            </div>
          </div>
        </Card>
      )}

      <Card className="mb-3 p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-1.5 text-[12px] text-stone-500">
              Species Threat Score
              <InfoTip text="0-100 Layer A score based on threatened species proportion and severity." />
            </div>
            <div className="mt-1 text-[34px] leading-tight tracking-tight text-stone-900">
              {loading && !layerA ? "..." : score.toFixed(1)}
              <span className="text-[14px] text-stone-400">/100</span>
            </div>
            <div className="mt-1 text-[11px] text-stone-500">
              Last generated: {generatedAt}
            </div>
          </div>
          <RiskBadge level={riskLevel(score)} />
        </div>
        <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-stone-100">
          <div
            className="h-full bg-gradient-to-r from-emerald-500 via-amber-400 to-rose-500 transition-all"
            style={{ width: `${Math.min(100, score)}%` }}
          />
        </div>
      </Card>

      <div className="mb-6 grid grid-cols-2 gap-3">
        <Card className="p-4">
          <div className="text-[11px] text-stone-500">ALA records</div>
          <div className="mt-1 text-[22px] text-stone-900">{formatNumber(layerA?.total_ala_records)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] text-stone-500">Unique species queried</div>
          <div className="mt-1 text-[22px] text-stone-900">{formatNumber(layerA?.unique_species_count)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] text-stone-500">IUCN assessed</div>
          <div className="mt-1 text-[22px] text-stone-900">{formatNumber(layerA?.iucn_assessed_species)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] text-stone-500">Threatened CR/EN/VU</div>
          <div className="mt-1 text-[22px] text-rose-700">{formatNumber(layerA?.threatened_species_count)}</div>
        </Card>
      </div>

      <PanelHeader icon={Database} title="IUCN Category Breakdown" subtitle="Count of assessed species by category" />
      <Card className="mb-6 p-5">
        {breakdown.length === 0 && <EmptyRow label={loading ? "Loading IUCN category counts..." : "No assessed categories returned."} />}
        <div className="space-y-2.5">
          {breakdown.map(([label, count]) => {
            const code = categoryCode(label);
            const style = categoryStyles[code] ?? categoryStyles.DD;
            return (
              <div key={label} className="grid grid-cols-[32px_1fr_48px] items-center gap-2.5">
                <span className={`rounded px-1.5 py-0.5 text-center text-[10px] tracking-wider text-white ${style.bar}`}>
                  {code}
                </span>
                <div className="relative h-5 overflow-hidden rounded bg-stone-100">
                  <div className={`h-full ${style.bar} opacity-90`} style={{ width: `${(count / maxBreakdown) * 100}%` }} />
                  <span className="absolute inset-0 flex items-center px-2 text-[10px] text-stone-700">
                    {label.replace(`${code} `, "")}
                  </span>
                </div>
                <span className={`text-right text-[12px] tabular-nums ${style.text}`}>{count}</span>
              </div>
            );
          })}
        </div>
      </Card>

      <PanelHeader icon={AlertTriangle} title="Threatened Species" subtitle="Critically endangered, endangered, and vulnerable" />
      <div className="mb-6 space-y-2">
        {loading && !layerA && <EmptyRow label="Loading threatened species..." />}
        {layerA?.status === "loading" && <EmptyRow label="Spatial analysis is running for the resolved query..." />}
        {layerA?.status === "failed" && <EmptyRow label={layerA.error || "Spatial analysis failed."} />}
        {layerA?.status === "success" && threatenedSpecies.length === 0 && <EmptyRow label="No CR/EN/VU species returned for this Layer A run." />}
        {threatenedSpecies.slice(0, 8).map((species) => (
          <SpeciesRow key={`${species.scientific_name}-${species.iucn_category}`} species={species} />
        ))}
      </div>

      <PanelHeader icon={MapPinned} title="Sampled Species Records" subtitle="Top ALA species facets returned by the query" />
      <div className="mb-6 space-y-2">
        {loading && !layerA && <EmptyRow label="Loading species records..." />}
        {allSpecies.slice(0, 10).map((species) => (
          <SpeciesRow key={`${species.scientific_name}-${species.record_count}`} species={species} />
        ))}
      </div>

      <Card className="p-5">
        <div className="flex items-center gap-2 text-[12px] text-stone-500">
          <ShieldCheck className="size-4 text-emerald-600" />
          Backend data sources
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {(layerA?.data_sources ?? ["Atlas of Living Australia Biocache", "IUCN Red List v4"]).map((source) => (
            <Chip key={source} tone="emerald">{source}</Chip>
          ))}
        </div>
      </Card>
    </div>
  );
}
