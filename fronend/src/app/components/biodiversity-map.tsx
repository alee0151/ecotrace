import { useEffect, useMemo, useState } from "react";
import { Layers, MapPin } from "lucide-react";
import type { SpatialLayerAResponse, SpatialThreatenedOccurrence } from "../../lib/api";
import type { SpatialSite } from "./spatial-context-bar";

type LayerKey = "ala" | "capad" | "ibra" | "kba" | "snes";

interface NominatimResult {
  lat: string;
  lon: string;
  display_name?: string;
}

interface MapPoint {
  lat: number;
  lon: number;
  label: string;
}

const layerConfig: { key: LayerKey; label: string; swatch: string }[] = [
  { key: "ala", label: "Threatened Occurrences", swatch: "bg-rose-500" },
  { key: "capad", label: "CAPAD", swatch: "bg-emerald-500" },
  { key: "ibra", label: "IBRA", swatch: "bg-sky-500" },
  { key: "kba", label: "KBA", swatch: "bg-blue-600" },
  { key: "snes", label: "SNES", swatch: "bg-amber-500" },
];

function locationCountry(layerA?: SpatialLayerAResponse | null) {
  const inferred = layerA?.inferred_location;
  const location = layerA?.location && "country" in layerA.location ? layerA.location : null;
  return inferred?.country || location?.country || "Australia";
}

function locationState(layerA?: SpatialLayerAResponse | null) {
  const inferred = layerA?.inferred_location;
  const location = layerA?.location && "state" in layerA.location ? layerA.location : null;
  return layerA?.company?.state || inferred?.state || location?.state || "";
}

function locationPostcode(layerA?: SpatialLayerAResponse | null) {
  const inferred = layerA?.inferred_location;
  const location = layerA?.location && "postcode" in layerA.location ? layerA.location : null;
  return layerA?.company?.postcode || inferred?.postcode || location?.postcode || "";
}

function fallbackPoint(site: SpatialSite, layerA?: SpatialLayerAResponse | null): MapPoint {
  const inferred = layerA?.inferred_location;
  const location = layerA?.location;
  const locationLabel = location && "label" in location && typeof location.label === "string"
    ? location.label
    : null;

  return {
    lat: inferred?.lat ?? location?.lat ?? site.lat,
    lon: inferred?.lon ?? location?.lon ?? site.lon,
    label: inferred?.label || locationLabel || site.name,
  };
}

function bbox(lat: number, lon: number, radiusKm: number) {
  const latSpan = Math.max(0.03, Math.min(0.35, (radiusKm / 111.32) * 1.7));
  const lonSpan = latSpan / Math.max(0.35, Math.cos((lat * Math.PI) / 180));
  return `${lon - lonSpan},${lat - latSpan},${lon + lonSpan},${lat + latSpan}`;
}

function occurrenceColor(category?: string | null) {
  if (category === "CR") return "rgba(190,18,60,0.95)";
  if (category === "EN") return "rgba(225,29,72,0.9)";
  return "rgba(244,63,94,0.82)";
}

function projectOccurrence(center: MapPoint, radiusKm: number, occurrence: SpatialThreatenedOccurrence) {
  const safeRadiusKm = Math.max(radiusKm || 1, 1);
  const latKm = (occurrence.lat - center.lat) * 111.32;
  const lonKm = (occurrence.lon - center.lon) * 111.32 * Math.cos((center.lat * Math.PI) / 180);
  const x = 400 + (lonKm / safeRadiusKm) * 300;
  const y = 300 - (latKm / safeRadiusKm) * 220;
  return {
    x: Math.max(30, Math.min(770, x)),
    y: Math.max(30, Math.min(570, y)),
  };
}

export function BiodiversityMap({
  site,
  layerA,
  loading,
}: {
  site: SpatialSite;
  layerA?: SpatialLayerAResponse | null;
  loading?: boolean;
}) {
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>({
    ala: true,
    capad: false,
    ibra: false,
    kba: false,
    snes: false,
  });
  const [open, setOpen] = useState(false);
  const toggle = (k: LayerKey) => setLayers((s) => ({ ...s, [k]: !s[k] }));
  const companyName = layerA?.company?.legal_name || site.company;
  const postcode = locationPostcode(layerA);
  const state = locationState(layerA);
  const country = locationCountry(layerA);
  const queries = useMemo(() => {
    const full = [companyName, postcode, state, country].filter(Boolean).join(", ");
    const regional = [postcode, state, country].filter(Boolean).join(", ");
    return Array.from(new Set([full, regional].filter(Boolean)));
  }, [companyName, postcode, state, country]);
  const [mapPoint, setMapPoint] = useState<MapPoint>(() => fallbackPoint(site, layerA));
  const threatenedOccurrences = (layerA?.threatened_occurrences ?? [])
    .filter((occurrence) => Number.isFinite(occurrence.lat) && Number.isFinite(occurrence.lon))
    .slice(0, 120);
  const score = layerA?.species_threat_score ?? 0;
  const activeLayerCount = Object.values(layers).filter(Boolean).length;
  const mapUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(
    bbox(mapPoint.lat, mapPoint.lon, site.radiusKm),
  )}&layer=mapnik&marker=${encodeURIComponent(`${mapPoint.lat},${mapPoint.lon}`)}`;

  useEffect(() => {
    let cancelled = false;

    async function geocode() {
      for (const query of queries) {
        try {
          const params = new URLSearchParams({
            q: query,
            format: "jsonv2",
            limit: "1",
            countrycodes: country.toLowerCase() === "australia" ? "au" : "",
          });
          if (!params.get("countrycodes")) params.delete("countrycodes");

          const response = await fetch(`https://nominatim.openstreetmap.org/search?${params.toString()}`, {
            headers: { Accept: "application/json" },
          });
          if (!response.ok) continue;

          const data = (await response.json()) as NominatimResult[];
          const first = data[0];
          if (!first) continue;

          const lat = Number(first.lat);
          const lon = Number(first.lon);
          if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;

          if (!cancelled) {
            setMapPoint({
              lat,
              lon,
              label: first.display_name || query,
            });
          }
          return;
        } catch {
          // Try the next, less-specific query.
        }
      }

      if (!cancelled) setMapPoint(fallbackPoint(site, layerA));
    }

    void geocode();
    return () => {
      cancelled = true;
    };
  }, [country, layerA, queries, site]);

  return (
    <div className="relative h-full w-full overflow-hidden rounded-2xl border border-stone-200 bg-stone-100">
      <iframe
        title="Company biodiversity map"
        src={mapUrl}
        className="absolute inset-0 h-full w-full border-0"
        loading="lazy"
        referrerPolicy="no-referrer-when-downgrade"
      />
      <div className="pointer-events-none absolute inset-0 bg-white/5" />

      {/* IBRA region */}
      {layers.ibra && (
        <svg className="pointer-events-none absolute inset-0 h-full w-full opacity-70" viewBox="0 0 800 600" preserveAspectRatio="none">
          <polygon
            points="60,80 700,40 760,520 100,560"
            fill="rgba(14,165,233,0.06)"
            stroke="rgba(2,132,199,0.7)"
            strokeDasharray="6 4"
            strokeWidth="1.2"
          />
        </svg>
      )}

      {/* CAPAD hashed protected zones */}
      {layers.capad && (
        <svg className="pointer-events-none absolute inset-0 h-full w-full opacity-65" viewBox="0 0 800 600" preserveAspectRatio="none">
          <defs>
            <pattern id="hash-light" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="8" stroke="rgba(5,150,105,0.55)" strokeWidth="2" />
            </pattern>
          </defs>
          <path
            d="M120 200 Q 200 140 320 180 T 460 260 Q 420 360 300 380 T 140 320 Z"
            fill="url(#hash-light)"
            stroke="rgba(5,150,105,0.9)"
            strokeWidth="1.5"
          />
          <path
            d="M520 380 Q 600 340 680 400 Q 700 480 620 500 Q 540 480 520 420 Z"
            fill="url(#hash-light)"
            stroke="rgba(5,150,105,0.9)"
            strokeWidth="1.5"
          />
        </svg>
      )}

      {/* SNES habitat heatmap */}
      {layers.snes && (
        <div
          className="pointer-events-none absolute opacity-80"
          style={{
            left: "38%",
            top: "30%",
            width: "32%",
            height: "40%",
            background:
              "radial-gradient(circle, rgba(244,63,94,0.28) 0%, rgba(244,63,94,0.12) 42%, rgba(244,63,94,0) 72%)",
            filter: "blur(6px)",
          }}
        />
      )}

      {/* KBA outline */}
      {layers.kba && (
        <svg className="pointer-events-none absolute inset-0 h-full w-full opacity-75" viewBox="0 0 800 600" preserveAspectRatio="none">
          <polygon
            points="280,120 560,140 600,360 320,400 240,260"
            fill="none"
            stroke="rgba(37,99,235,0.85)"
            strokeWidth="2"
            strokeDasharray="2 4"
          />
        </svg>
      )}

      {/* ALA threatened species occurrence points */}
      {layers.ala && (
        <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 800 600" preserveAspectRatio="none">
          {threatenedOccurrences.map((occurrence, i) => {
            const point = projectOccurrence(mapPoint, site.radiusKm, occurrence);
            const r = occurrence.iucn_category === "CR" ? 4 : occurrence.iucn_category === "EN" ? 3.4 : 2.8;
            return (
              <circle
                key={`${occurrence.occurrence_id || occurrence.scientific_name}-${i}`}
                cx={point.x}
                cy={point.y}
                r={r}
                fill={occurrenceColor(occurrence.iucn_category)}
                stroke="rgba(255,255,255,0.9)"
                strokeWidth="1"
              >
                <title>
                  {occurrence.scientific_name}
                  {occurrence.common_name ? ` (${occurrence.common_name})` : ""}
                  {occurrence.iucn_category ? ` - ${occurrence.iucn_category}` : ""}
                </title>
              </circle>
            );
          })}
        </svg>
      )}

      <div className="pointer-events-none absolute left-4 top-4 max-w-[calc(100%-6rem)] rounded-lg bg-white/95 px-3 py-2 text-[11px] text-stone-700 shadow-sm ring-1 ring-stone-200/80">
        <div className="flex min-w-0 items-center gap-2">
          <MapPin className="size-3.5 shrink-0 text-emerald-700" />
          <div className="min-w-0">
            <div className="truncate text-[12px] font-medium text-stone-900">
              {site.company}
            </div>
            <div className="truncate text-stone-500">
              {mapPoint.lat.toFixed(4)}, {mapPoint.lon.toFixed(4)} | {site.radiusKm} km radius
            </div>
          </div>
        </div>
      </div>

      <div className="pointer-events-none absolute bottom-4 left-4 flex max-w-[calc(100%-2rem)] flex-wrap items-center gap-2 rounded-lg bg-white/95 px-3 py-2 text-[11px] text-stone-600 shadow-sm ring-1 ring-stone-200/80">
        <span className="text-stone-500">Layer A</span>
        <span className="font-mono text-stone-900">{loading ? "..." : `${score.toFixed(1)}/100`}</span>
        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-stone-100">
          <div
            className="h-full bg-gradient-to-r from-emerald-500 via-amber-400 to-rose-500 transition-all"
            style={{ width: `${Math.min(100, score)}%` }}
          />
        </div>
        <span>{threatenedOccurrences.length} occurrences</span>
        <span className="text-stone-300">|</span>
        <span>{layerA?.threatened_species_count ?? 0} CR/EN/VU species</span>
      </div>

      {/* Map controls */}
      <div className="absolute right-4 top-4 flex flex-col items-end gap-2">
        <div className="w-56 overflow-hidden rounded-lg bg-white/95 ring-1 ring-stone-200/80 shadow-sm">
          <button
            onClick={() => setOpen((o) => !o)}
            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[12px] text-stone-700 hover:bg-stone-50"
          >
            <span className="flex items-center gap-2">
              <Layers className="size-3.5 text-emerald-600" />
              Map Layers
            </span>
            <span className="text-[10px] text-stone-400">
              {activeLayerCount}/5
            </span>
          </button>
          {open && (
            <div className="border-t border-stone-200 p-2">
              {layerConfig.map((l) => (
                <label
                  key={l.key}
                  className="flex cursor-pointer items-center justify-between gap-2 rounded px-2 py-1.5 text-[12px] text-stone-700 hover:bg-stone-50"
                >
                  <span className="flex items-center gap-2">
                    <span className={`size-2.5 rounded-sm ${l.swatch}`} />
                    {l.label}
                  </span>
                  <button
                    type="button"
                    onClick={() => toggle(l.key)}
                    className={`relative h-4 w-7 rounded-full transition ${
                      layers[l.key] ? "bg-emerald-500" : "bg-stone-300"
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 size-3 rounded-full bg-white transition shadow ${
                        layers[l.key] ? "left-3.5" : "left-0.5"
                      }`}
                    />
                  </button>
                </label>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
