import { Network, Building, AlertCircle } from 'lucide-react';

interface SupplyChainNode {
  id: string;
  name: string;
  type: 'parent' | 'subsidiary' | 'supplier';
  riskLevel: 'Low' | 'Medium' | 'High';
}

interface SupplyChainMapProps {
  nodes: SupplyChainNode[];
}

export function SupplyChainMap({ nodes }: SupplyChainMapProps) {
  const getRiskColor = (level: string) => {
    switch (level) {
      case 'Low': return 'bg-emerald-500';
      case 'Medium': return 'bg-amber-500';
      case 'High': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  const parent = nodes.find(n => n.type === 'parent');
  const subsidiaries = nodes.filter(n => n.type === 'subsidiary');
  const suppliers = nodes.filter(n => n.type === 'supplier');

  return (
    <div className="w-full max-w-6xl bg-white rounded-xl border-2 border-gray-200 p-8">
      <div className="flex items-center gap-3 mb-6">
        <Network className="text-emerald-600" size={24} />
        <h2 className="text-2xl font-semibold text-gray-900">Supply Chain Network</h2>
      </div>

      <div className="flex flex-col items-center gap-8">
        {/* Parent Company */}
        {parent && (
          <div className="relative">
            <div className="flex flex-col items-center">
              <div className={`w-4 h-4 rounded-full ${getRiskColor(parent.riskLevel)} mb-2`} />
              <div className="px-6 py-4 bg-emerald-50 border-2 border-emerald-200 rounded-xl text-center">
                <Building className="mx-auto mb-2 text-emerald-600" size={20} />
                <div className="font-semibold text-gray-900">{parent.name}</div>
                <div className="text-sm text-gray-600">Parent Company</div>
              </div>
            </div>
          </div>
        )}

        {/* Subsidiaries */}
        {subsidiaries.length > 0 && (
          <div className="w-full">
            <div className="text-sm font-medium text-gray-600 mb-3 text-center">Subsidiaries</div>
            <div className="grid grid-cols-3 gap-4">
              {subsidiaries.map((node) => (
                <div key={node.id} className="flex flex-col items-center">
                  <div className="h-8 w-0.5 bg-gray-300 mb-2" />
                  <div className={`w-3 h-3 rounded-full ${getRiskColor(node.riskLevel)} mb-2`} />
                  <div className="px-4 py-3 bg-blue-50 border border-blue-200 rounded-lg text-center w-full">
                    <div className="text-sm font-medium text-gray-900">{node.name}</div>
                    <div className="text-xs text-gray-600 mt-1">Risk: {node.riskLevel}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Suppliers */}
        {suppliers.length > 0 && (
          <div className="w-full">
            <div className="text-sm font-medium text-gray-600 mb-3 text-center">Tier-1 Suppliers</div>
            <div className="grid grid-cols-2 gap-4">
              {suppliers.map((node) => (
                <div key={node.id} className="flex flex-col items-center">
                  <div className="h-8 w-0.5 bg-gray-300 mb-2" />
                  <div className={`w-3 h-3 rounded-full ${getRiskColor(node.riskLevel)} mb-2`} />
                  <div className="px-4 py-3 bg-purple-50 border border-purple-200 rounded-lg text-center w-full">
                    <div className="text-sm font-medium text-gray-900">{node.name}</div>
                    <div className="text-xs text-gray-600 mt-1">Risk: {node.riskLevel}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-6 pt-6 border-t border-gray-200">
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-emerald-500" />
            <span className="text-gray-600">Low Risk</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-amber-500" />
            <span className="text-gray-600">Medium Risk</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-red-500" />
            <span className="text-gray-600">High Risk</span>
          </div>
        </div>
      </div>
    </div>
  );
}
