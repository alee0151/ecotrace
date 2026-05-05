import { useCallback, useEffect, useState } from "react";
import { PageShell } from "../components/PageShell";
import {
  SpatialContextBar,
  spatialSites,
  type SpatialSite,
} from "../components/spatial-context-bar";
import { FindingsPanel } from "../components/findings-panel";
import { BiodiversityMap } from "../components/biodiversity-map";
import { Card, Stat } from "../components/shared";
import {
  getSpatialAnalysisForQuery,
  getSpatialLayerA,
  type SpatialLayerAResponse,
} from "../../lib/api";
import { evidenceAnalysisComplete, loadCompanyAnalysis } from "../lib/analysis";

function formatNumber(value?: number) {
  return new Intl.NumberFormat("en-AU").format(value ?? 0);
}

function scoreTone(score?: number): "up" | "down" | "flat" {
  if (score === undefined) return "flat";
  if (score >= 60) return "down";
  if (score >= 35) return "flat";
  return "up";
}

function persistSpatialScore(data: SpatialLayerAResponse) {
  if (data.status !== "success" || typeof data.species_threat_score !== "number") return;

  localStorage.setItem("latest_spatial_analysis", JSON.stringify(data));

  try {
    const raw = localStorage.getItem("company_analysis");
    if (!raw) return;

    const analysis = JSON.parse(raw);
    if (!evidenceAnalysisComplete(analysis, data.query_id)) return;
    if (analysis?.query_id && data.query_id && analysis.query_id !== data.query_id) return;
    if (
      typeof analysis?.spatial_analysis?.combined_biodiversity_score === "number" &&
      typeof data.combined_biodiversity_score !== "number"
    ) return;

    localStorage.setItem(
      "company_analysis",
      JSON.stringify({ ...analysis, spatial_analysis: data }),
    );
  } catch {
    // Keep the spatial page usable even if a previous localStorage payload is stale.
  }
}

export function SpatialAnalysisPage() {
  const [site, setSite] = useState<SpatialSite>(spatialSites[0]);
  const [layerA, setLayerA] = useState<SpatialLayerAResponse | null>(null);
  const [queryId, setQueryId] = useState<string | null>(() => localStorage.getItem("query_id"));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshIndex, setRefreshIndex] = useState(0);
  const [forceRefresh, setForceRefresh] = useState(false);
  const analysis = loadCompanyAnalysis();
  const queryEvidenceReady = evidenceAnalysisComplete(analysis, queryId);

  const refreshLayerA = useCallback(() => {
    setForceRefresh(true);
    setRefreshIndex((value) => value + 1);
  }, []);

  const siteFromSpatialResponse = useCallback((data: SpatialLayerAResponse): SpatialSite | null => {
    const inferred = data.inferred_location ?? (data.location && "label" in data.location ? data.location : null);
    const company = data.company;
    if (!inferred || !company) return null;
    const evidenceDerived = [
      "report_or_news_evidence",
      "inferred_location_report",
      "inferred_location_news",
    ].includes(inferred.source || "");
    const sourceLabel = evidenceDerived ? "Source: Extracted evidence" : "Source: ABN Registration";
    const sectorLabel = evidenceDerived
      ? `Evidence location - ${inferred.state || "AU"}`
      : company.state ? `Registered address - ${company.state}` : "Registered address";

    return {
      id: data.query?.query_id || data.query_id || "resolved-query",
      name: inferred.label || `${company.state || "AU"} ${company.postcode || ""}`.trim(),
      lat: inferred.lat,
      lon: inferred.lon,
      radiusKm: inferred.radius_km,
      company: company.legal_name || data.query?.input_value || "Resolved company",
      ticker: company.entity_type || "ABR",
      sector: sectorLabel,
      abn: company.abn || "N/A",
      locationMethod: inferred.method,
      locationConfidence: inferred.confidence,
      sourceTags: [
        { label: sourceLabel, tone: "emerald" as const },
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

    if (queryId && !queryEvidenceReady) {
      setLayerA(null);
      setLoading(false);
      return;
    }

    const request = queryId
      ? getSpatialAnalysisForQuery(queryId, forceRefresh)
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
          persistSpatialScore(data);
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
          setForceRefresh(false);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      if (poll) window.clearTimeout(poll);
    };
  }, [forceRefresh, queryEvidenceReady, queryId, refreshIndex, site.lat, site.lon, site.radiusKm, siteFromSpatialResponse]);

  const handleSiteChange = (nextSite: SpatialSite) => {
    setQueryId(null);
    setSite(nextSite);
  };

  const siteOptions = queryId ? [site] : spatialSites;
  const spatialLocked = Boolean(queryId && !queryEvidenceReady);
  const statusHint = queryId && layerA?.status === "loading"
    ? "Spatial analysis is running from the resolved search query"
    : queryId && !queryEvidenceReady
      ? "Waiting for news and report evidence analysis"
      : queryId
      ? "Spatial analysis inferred from the latest resolved search query"
      : "Demo spatial site";

  return (
    <PageShell
      sectionMarker="  SPATIAL ANALYSIS"
      coords={`LAT ${site.lat.toFixed(4)} deg  LON ${site.lon.toFixed(4)} deg  |  RADIUS ${site.radiusKm} KM`}
    >
      <SpatialContextBar site={site} sites={siteOptions} onSiteChange={handleSiteChange} />

      {spatialLocked ? (
        <Card className="p-6">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-stone-400">
            Layer A queued
          </div>
          <div className="mt-2 text-[18px] text-stone-900">
            Spatial species analysis will appear after news and report evidence completes.
          </div>
          <div className="mt-1 text-[13px] text-stone-500">
            This keeps the IUCN layer tied to the final evidence-derived location instead of showing an early ABN-only spatial result.
          </div>
        </Card>
      ) : (
        <>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Stat
          label="Species Threat Score"
          value={loading && !layerA ? "..." : `${(layerA?.species_threat_score ?? 0).toFixed(1)}`}
          delta="Proportional 0-100 Layer A score"
          tone={scoreTone(layerA?.species_threat_score)}
          hint="Threatened species proportion + severity"
        />
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
        </>
      )}
    </PageShell>
  );
}
