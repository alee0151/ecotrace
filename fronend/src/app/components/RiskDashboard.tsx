import { AlertTriangle, MapPin, TrendingUp, FileText } from 'lucide-react';

interface RiskData {
  overallScore: number;
  riskLevel: 'Low' | 'Medium' | 'High' | 'Critical';
  protectedAreas: number;
  threatenedSpecies: number;
  recentIncidents: number;
}

interface RiskDashboardProps {
  riskData: RiskData;
}

export function RiskDashboard({ riskData }: RiskDashboardProps) {
  const getRiskColor = (level: string) => {
    switch (level) {
      case 'Low': return 'text-emerald-600 bg-emerald-50 border-emerald-200';
      case 'Medium': return 'text-amber-600 bg-amber-50 border-amber-200';
      case 'High': return 'text-orange-600 bg-orange-50 border-orange-200';
      case 'Critical': return 'text-red-600 bg-red-50 border-red-200';
      default: return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  return (
    <div className="w-full max-w-6xl">
      <h2 className="text-2xl font-semibold text-gray-900 mb-6">Biodiversity Risk Analysis</h2>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className={`p-6 rounded-xl border-2 ${getRiskColor(riskData.riskLevel)}`}>
          <div className="flex items-center gap-3 mb-2">
            <AlertTriangle size={24} />
            <span className="text-sm font-medium">Overall Risk</span>
          </div>
          <div className="text-3xl font-bold">{riskData.riskLevel}</div>
          <div className="text-sm opacity-80 mt-1">Score: {riskData.overallScore}/100</div>
        </div>

        <div className="p-6 rounded-xl border-2 bg-blue-50 border-blue-200 text-blue-600">
          <div className="flex items-center gap-3 mb-2">
            <MapPin size={24} />
            <span className="text-sm font-medium">Protected Areas</span>
          </div>
          <div className="text-3xl font-bold">{riskData.protectedAreas}</div>
          <div className="text-sm opacity-80 mt-1">Overlapping sites</div>
        </div>

        <div className="p-6 rounded-xl border-2 bg-purple-50 border-purple-200 text-purple-600">
          <div className="flex items-center gap-3 mb-2">
            <TrendingUp size={24} />
            <span className="text-sm font-medium">Threatened Species</span>
          </div>
          <div className="text-3xl font-bold">{riskData.threatenedSpecies}</div>
          <div className="text-sm opacity-80 mt-1">Within range</div>
        </div>

        <div className="p-6 rounded-xl border-2 bg-gray-50 border-gray-200 text-gray-600">
          <div className="flex items-center gap-3 mb-2">
            <FileText size={24} />
            <span className="text-sm font-medium">Recent Incidents</span>
          </div>
          <div className="text-3xl font-bold">{riskData.recentIncidents}</div>
          <div className="text-sm opacity-80 mt-1">Last 12 months</div>
        </div>
      </div>
    </div>
  );
}
