import { useCallback, useEffect, useState } from "react";
import { PageShell } from "../components/PageShell";
import {
  SpatialContextBar,
  spatialSites,
  type SpatialSite,
} from "../components/spatial-context-bar";
import { FindingsPanel } from "../components/findings-panel";
import { BiodiversityMap } from "../components/biodiversity-map";
import { Stat } from "../components/shared";
import {
  getSpatialAnalysisForQuery,
  getSpatialLayerA,
  type SpatialLayerAResponse,
} from "../../lib/api";

function formatNumber(value?: number) {
  return new Intl.NumberFormat("en-AU").format(value ?? 0);
}

function scoreTone(score?: number): "up" | "down" | "flat" {
  if (score === undefined) return "flat";
  if (score >= 60) return "down";
  if (score >= 35) return "flat";
  return "up";
}

export function SpatialAnalysisPage() {
  const [site, setSite] = useState<SpatialSite>(spatialSites[0]);
  const [layerA, setLayerA] = useState<SpatialLayerAResponse | null>(null);
  const [queryId, setQueryId] = useState<string | null>(() => localStorage.getItem("query_id"));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshIndex, setRefreshIndex] = useState(0);

  const refreshLayerA = useCallback(() => {
    setRefreshIndex((value) => value + 1);
  }, []);

  const siteFromSpatialResponse = useCallback((data: SpatialLayerAResponse): SpatialSite | null => {
    const inferred = data.inferred_location ?? (data.location && "label" in data.location ? data.location : null);
    const company = data.company;
    if (!inferred || !company) return null;

    return {
      id: data.query?.query_id || data.query_id || "resolved-query",
      name: inferred.label || `${company.state || "AU"} ${company.postcode || ""}`.trim(),
      lat: inferred.lat,
      lon: inferred.lon,
      radiusKm: inferred.radius_km,
      company: company.legal_name || data.query?.input_value || "Resolved company",
      ticker: company.entity_type || "ABR",
      sector: company.state ? `Registered address · ${company.state}` : "Registered address",
      abn: company.abn || "N/A",
      locationMethod: inferred.method,
      locationConfidence: inferred.confidence,
      sourceTags: [
        { label: "Source: ABN Registration", tone: "emerald" as const },
        { label: `Inference: ${inferred.method}`, tone: "blue" as const },
        { label: "Layer A: ALA + IUCN", tone: "amber" as const },
      ],
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let poll: number | undefined;

    setLoading(true);
    setError(null);

    const request = queryId
      ? getSpatialAnalysisForQuery(queryId)
      : getSpatialLayerA({
          lat: site.lat,
          lon: site.lon,
          radius_km: site.radiusKm,
          max_species: 50,
        });

    request
      .then((data) => {
        if (!cancelled) {
          setLayerA(data);
          const dynamicSite = siteFromSpatialResponse(data);
          if (dynamicSite) {
            setSite(dynamicSite);
          }
          if (queryId && data.status === "loading") {
            poll = window.setTimeout(() => {
              setRefreshIndex((value) => value + 1);
            }, 5000);
          }
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      if (poll) window.clearTimeout(poll);
    };
  }, [queryId, refreshIndex, site.lat, site.lon, site.radiusKm, siteFromSpatialResponse]);

  const handleSiteChange = (nextSite: SpatialSite) => {
    setQueryId(null);
    setSite(nextSite);
  };

  const siteOptions = queryId ? [site] : spatialSites;
  const statusHint = queryId && layerA?.status === "loading"
    ? "Spatial analysis is running from the resolved search query"
    : queryId
      ? "Spatial analysis inferred from the latest resolved search query"
      : "Demo spatial site";

  return (
    <PageShell
      sectionMarker="  SPATIAL ANALYSIS"
      coords={`LAT ${site.lat.toFixed(4)}°  LON ${site.lon.toFixed(4)}°  ·  RADIUS ${site.radiusKm} KM`}
    >
      <SpatialContextBar site={site} sites={siteOptions} onSiteChange={handleSiteChange} />

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Stat
          label="ALA Occurrence Records"
          value={loading && !layerA ? "..." : formatNumber(layerA?.total_ala_records)}
          delta={`${formatNumber(layerA?.unique_species_count)} species queried`}
          tone="flat"
          hint={statusHint}
        />
        <Stat
          label="Threatened (CR+EN+VU)"
          value={loading && !layerA ? "..." : formatNumber(layerA?.threatened_species_count)}
          delta={`${formatNumber(layerA?.iucn_assessed_species)} IUCN assessed`}
          tone={(layerA?.threatened_species_count ?? 0) > 0 ? "down" : "up"}
          hint="IUCN Red List v4"
        />
        <Stat
          label="Species Threat Score"
          value={loading && !layerA ? "..." : `${(layerA?.species_threat_score ?? 0).toFixed(1)}`}
          delta="Weighted 0-100 Layer A score"
          tone={scoreTone(layerA?.species_threat_score)}
          hint="IUCN category x occurrence count"
        />
        <Stat
          label="Analysis Radius"
          value={`${site.radiusKm} km`}
          delta={`${site.lat.toFixed(4)}, ${site.lon.toFixed(4)}`}
          tone="flat"
          hint={site.name}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <div className="lg:col-span-5 min-h-[720px]">
          <FindingsPanel
            layerA={layerA}
            loading={loading}
            error={error}
            onRetry={refreshLayerA}
          />
        </div>
        <div className="lg:col-span-7 min-h-[720px]">
          <BiodiversityMap site={site} layerA={layerA} loading={loading} />
        </div>
      </div>
    </PageShell>
  );
}
