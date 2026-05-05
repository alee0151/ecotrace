import { useState } from "react";
import { Layers, Plus, Minus, Maximize2, Crosshair, MapPin } from "lucide-react";
import type { SpatialLayerAResponse } from "../../lib/api";
import type { SpatialSite } from "./spatial-context-bar";

type LayerKey = "ala" | "capad" | "ibra" | "kba" | "snes";

const layerConfig: { key: LayerKey; label: string; swatch: string }[] = [
  { key: "ala", label: "ALA Occurrences", swatch: "bg-amber-500" },
  { key: "capad", label: "CAPAD Polygons", swatch: "bg-emerald-500" },
  { key: "ibra", label: "IBRA Regions", swatch: "bg-sky-500" },
  { key: "kba", label: "KBA Zones", swatch: "bg-blue-600" },
  { key: "snes", label: "SNES Habitats", swatch: "bg-rose-500" },
];

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
    capad: true,
    ibra: false,
    kba: true,
    snes: true,
  });
  const [open, setOpen] = useState(true);
  const toggle = (k: LayerKey) => setLayers((s) => ({ ...s, [k]: !s[k] }));
  const occurrenceDots = Math.max(16, Math.min(120, layerA?.unique_species_count ?? 80));
  const score = layerA?.species_threat_score ?? 0;

  return (
    <div className="relative h-full w-full overflow-hidden rounded-2xl bg-gradient-to-br from-emerald-50 to-sky-50 border border-stone-200">
      {/* Topographic backdrop */}
      <svg className="absolute inset-0 h-full w-full opacity-30" viewBox="0 0 800 600" preserveAspectRatio="none">
        {Array.from({ length: 18 }).map((_, i) => (
          <path
            key={i}
            d={`M0 ${40 + i * 32} Q ${200 + i * 10} ${20 + i * 28}, 400 ${60 + i * 30} T 800 ${30 + i * 32}`}
            stroke="#059669"
            strokeWidth="0.6"
            fill="none"
          />
        ))}
      </svg>

      {/* Subtle grid */}
      <div
        className="absolute inset-0 opacity-40"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(120,113,108,0.08) 1px, transparent 1px), linear-gradient(to bottom, rgba(120,113,108,0.08) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />

      {/* IBRA region */}
      {layers.ibra && (
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 800 600" preserveAspectRatio="none">
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
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 800 600" preserveAspectRatio="none">
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
          className="absolute"
          style={{
            left: "38%",
            top: "30%",
            width: "32%",
            height: "40%",
            background:
              "radial-gradient(circle, rgba(244,63,94,0.45) 0%, rgba(244,63,94,0.18) 40%, rgba(244,63,94,0) 70%)",
            filter: "blur(6px)",
          }}
        />
      )}

      {/* KBA outline */}
      {layers.kba && (
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 800 600" preserveAspectRatio="none">
          <polygon
            points="280,120 560,140 600,360 320,400 240,260"
            fill="none"
            stroke="rgba(37,99,235,0.85)"
            strokeWidth="2"
            strokeDasharray="2 4"
          />
        </svg>
      )}

      {/* ALA occurrence dots */}
      {layers.ala && (
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 800 600" preserveAspectRatio="none">
          {Array.from({ length: occurrenceDots }).map((_, i) => {
            const x = 80 + ((i * 53) % 660);
            const y = 60 + ((i * 71) % 480);
            const r = 1.5 + (i % 3) * 0.6;
            return <circle key={i} cx={x} cy={y} r={r} fill="rgba(217,119,6,0.85)" />;
          })}
        </svg>
      )}

      {/* Site marker */}
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
        <div className="relative flex size-16 items-center justify-center">
          <div className="absolute inset-0 animate-ping rounded-full bg-emerald-400/30" />
          <div className="absolute inset-3 rounded-full bg-emerald-400/40" />
          <div className="relative flex size-7 items-center justify-center rounded-full bg-emerald-600 shadow-lg ring-2 ring-white">
            <MapPin className="size-4 text-white" />
          </div>
        </div>
        <div className="mt-2 -translate-x-1/2 translate-x-8 whitespace-nowrap rounded-md bg-white/95 px-2 py-1 text-[11px] text-stone-800 ring-1 ring-stone-200 shadow-sm">
          {site.company} - {site.name}
          <div className="text-[10px] text-stone-500">
            {site.lat.toFixed(4)}, {site.lon.toFixed(4)} | {site.radiusKm} km radius
          </div>
        </div>
      </div>

      {/* Scale + coordinates */}
      <div className="absolute bottom-4 left-4 flex items-center gap-3 rounded-lg bg-white/95 px-3 py-2 text-[11px] text-stone-600 ring-1 ring-stone-200 shadow-sm">
        <Crosshair className="size-3.5 text-emerald-600" />
        <span className="font-mono">
          {Math.abs(site.lat).toFixed(2)} deg {site.lat < 0 ? "S" : "N"},{" "}
          {Math.abs(site.lon).toFixed(2)} deg {site.lon < 0 ? "W" : "E"}
        </span>
        <span className="text-stone-300">|</span>
        <div className="flex items-center gap-2">
          <div className="h-1 w-12 bg-stone-700" />
          <span>2 km</span>
        </div>
      </div>

      <div className="absolute bottom-4 right-4 w-64 rounded-lg bg-white/95 p-3 text-[11px] ring-1 ring-stone-200 shadow-sm">
        <div className="flex items-center justify-between">
          <span className="text-stone-500">Layer A species threat score</span>
          <span className="font-mono text-stone-900">
            {loading ? "..." : `${score.toFixed(1)}/100`}
          </span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-stone-100">
          <div
            className="h-full bg-gradient-to-r from-emerald-500 via-amber-400 to-rose-500 transition-all"
            style={{ width: `${Math.min(100, score)}%` }}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-stone-500">
          <span>{layerA?.unique_species_count ?? 0} species queried</span>
          <span>{layerA?.threatened_species_count ?? 0} CR/EN/VU</span>
        </div>
      </div>

      {/* Map controls */}
      <div className="absolute right-4 top-4 flex flex-col gap-2">
        <div className="flex flex-col overflow-hidden rounded-lg bg-white/95 ring-1 ring-stone-200 shadow-sm">
          <button className="p-2 text-stone-600 hover:bg-stone-50">
            <Plus className="size-4" />
          </button>
          <div className="h-px bg-stone-200" />
          <button className="p-2 text-stone-600 hover:bg-stone-50">
            <Minus className="size-4" />
          </button>
          <div className="h-px bg-stone-200" />
          <button className="p-2 text-stone-600 hover:bg-stone-50">
            <Maximize2 className="size-4" />
          </button>
        </div>

        <div className="w-60 overflow-hidden rounded-lg bg-white/95 ring-1 ring-stone-200 shadow-sm">
          <button
            onClick={() => setOpen((o) => !o)}
            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[12px] text-stone-700 hover:bg-stone-50"
          >
            <span className="flex items-center gap-2">
              <Layers className="size-3.5 text-emerald-600" />
              Map Layers
            </span>
            <span className="text-[10px] text-stone-400">
              {Object.values(layers).filter(Boolean).length}/5 active
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
