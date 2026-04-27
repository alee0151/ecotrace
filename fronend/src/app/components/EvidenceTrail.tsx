import { FileText, Link as LinkIcon, MapPin, Calendar, ExternalLink } from 'lucide-react';

interface Evidence {
  id: string;
  type: 'report' | 'news' | 'regulatory' | 'spatial';
  title: string;
  source: string;
  date: string;
  claim: string;
  confidence: number;
  location?: string;
}

interface EvidenceTrailProps {
  evidence: Evidence[];
}

export function EvidenceTrail({ evidence }: EvidenceTrailProps) {
  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'report': return <FileText size={20} />;
      case 'news': return <LinkIcon size={20} />;
      case 'regulatory': return <FileText size={20} />;
      case 'spatial': return <MapPin size={20} />;
      default: return <FileText size={20} />;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'report': return 'bg-blue-50 text-blue-600 border-blue-200';
      case 'news': return 'bg-purple-50 text-purple-600 border-purple-200';
      case 'regulatory': return 'bg-red-50 text-red-600 border-red-200';
      case 'spatial': return 'bg-emerald-50 text-emerald-600 border-emerald-200';
      default: return 'bg-gray-50 text-gray-600 border-gray-200';
    }
  };

  return (
    <div className="w-full max-w-6xl">
      <h2 className="text-2xl font-semibold text-gray-900 mb-6">Evidence & Audit Trail</h2>

      <div className="space-y-4">
        {evidence.map((item) => (
          <div key={item.id} className="bg-white rounded-xl border-2 border-gray-200 p-6">
            <div className="flex items-start gap-4">
              <div className={`p-3 rounded-lg border ${getTypeColor(item.type)}`}>
                {getTypeIcon(item.type)}
              </div>

              <div className="flex-1">
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-semibold text-gray-900">{item.title}</h3>
                  <button className="text-emerald-600 hover:text-emerald-700 flex items-center gap-1 text-sm">
                    <span>View Source</span>
                    <ExternalLink size={14} />
                  </button>
                </div>

                <div className="flex items-center gap-4 text-sm text-gray-600 mb-3">
                  <div className="flex items-center gap-1">
                    <LinkIcon size={14} />
                    <span>{item.source}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Calendar size={14} />
                    <span>{item.date}</span>
                  </div>
                  {item.location && (
                    <div className="flex items-center gap-1">
                      <MapPin size={14} />
                      <span>{item.location}</span>
                    </div>
                  )}
                </div>

                <p className="text-gray-700 mb-3">{item.claim}</p>

                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-700">Confidence:</span>
                  <div className="flex-1 max-w-xs bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-emerald-600 h-2 rounded-full"
                      style={{ width: `${item.confidence}%` }}
                    />
                  </div>
                  <span className="text-sm text-gray-600">{item.confidence}%</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
