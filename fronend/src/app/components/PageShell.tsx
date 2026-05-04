import { ReactNode } from "react";

export function TopoBackdrop() {
  return (
    <svg
      className="absolute inset-x-0 top-0 w-full h-[420px] opacity-[0.18] pointer-events-none"
      viewBox="0 0 1200 420"
      preserveAspectRatio="none"
    >
      {Array.from({ length: 9 }).map((_, i) => (
        <path
          key={i}
          d={`M0 ${60 + i * 36} Q 300 ${20 + i * 36} 600 ${70 + i * 36} T 1200 ${50 + i * 36}`}
          fill="none"
          stroke="#047857"
          strokeWidth="0.6"
        />
      ))}
    </svg>
  );
}

export function PageShell({
  children,
  sectionMarker,
  coords,
  className = "",
  fullBleed = false,
}: {
  children: ReactNode;
  sectionMarker?: string;
  coords?: string;
  className?: string;
  fullBleed?: boolean;
}) {
  return (
    <div
      className={`relative min-h-[calc(100vh-65px)] bg-gradient-to-b from-[#f5f3ee] via-[#eef1ec] to-[#e3ebe4] ${className}`}
    >
      <TopoBackdrop />
      {sectionMarker && (
        <div className="absolute top-6 right-8 text-[10px] font-mono tracking-[0.25em] uppercase text-emerald-800/60 pointer-events-none z-10">
          {sectionMarker}
        </div>
      )}
      <div className={`relative ${fullBleed ? "p-6" : "p-8 max-w-[1400px] mx-auto"}`}>
        {coords && (
          <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-stone-500 mb-3">
            {coords}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}


export function SectionMono({ children }: { children: ReactNode }) {
  return (
    <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-emerald-800/70 mb-2">{children}</div>
  );
}
