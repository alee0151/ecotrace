import { Building2, CheckCircle, AlertCircle } from 'lucide-react';

interface CompanyResolutionProps {
  resolvedCompany: {
    name: string;
    abn: string;
    legalName: string;
    industry: string;
    confidence: number;
    verified: boolean;
  } | null;
}

export function CompanyResolution({ resolvedCompany }: CompanyResolutionProps) {
  if (!resolvedCompany) return null;

  return (
    <div className="w-full max-w-3xl bg-white rounded-xl border-2 border-gray-200 p-6">
      <div className="flex items-start gap-4">
        <div className="p-3 bg-emerald-50 rounded-lg">
          <Building2 className="text-emerald-600" size={24} />
        </div>

        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="text-xl font-semibold text-gray-900">{resolvedCompany.name}</h3>
            {resolvedCompany.verified ? (
              <CheckCircle className="text-emerald-600" size={20} />
            ) : (
              <AlertCircle className="text-amber-500" size={20} />
            )}
          </div>

          <div className="space-y-2 text-sm text-gray-600">
            <div className="flex gap-2">
              <span className="font-medium">Legal Name:</span>
              <span>{resolvedCompany.legalName}</span>
            </div>
            <div className="flex gap-2">
              <span className="font-medium">ABN:</span>
              <span>{resolvedCompany.abn}</span>
            </div>
            <div className="flex gap-2">
              <span className="font-medium">Industry:</span>
              <span>{resolvedCompany.industry}</span>
            </div>
          </div>

          <div className="mt-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-medium text-gray-700">Match Confidence</span>
              <span className="text-sm text-gray-500">{resolvedCompany.confidence}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-emerald-600 h-2 rounded-full transition-all"
                style={{ width: `${resolvedCompany.confidence}%` }}
              />
            </div>
          </div>

          {!resolvedCompany.verified && (
            <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <p className="text-sm text-amber-800">
                Please confirm this is the correct entity before viewing the analysis.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
