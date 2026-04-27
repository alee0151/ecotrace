import { MapPin, Leaf, Shield } from 'lucide-react';

interface Location {
  id: string;
  name: string;
  lat: number;
  lng: number;
  type: 'facility' | 'protected' | 'species';
  riskLevel: 'Low' | 'Medium' | 'High';
}

interface SpatialMapProps {
  locations: Location[];
}

export function SpatialMap({ locations }: SpatialMapProps) {
  const getLocationIcon = (type: string) => {
    switch (type) {
      case 'facility': return <MapPin size={16} />;
      case 'protected': return <Shield size={16} />;
      case 'species': return <Leaf size={16} />;
      default: return <MapPin size={16} />;
    }
  };

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'Low': return 'bg-emerald-500';
      case 'Medium': return 'bg-amber-500';
      case 'High': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <div className="w-full max-w-6xl bg-white rounded-xl border-2 border-gray-200 p-8">
      <h2 className="text-2xl font-semibold text-gray-900 mb-6">Spatial Analysis</h2>

      {/* Simulated Map */}
      <div className="relative w-full h-96 bg-gradient-to-br from-emerald-50 to-blue-50 rounded-xl border-2 border-gray-200 mb-6 overflow-hidden">
        <div className="absolute inset-0 bg-grid-pattern opacity-20" />

        {/* Location Markers */}
        {locations.map((location, index) => (
          <div
            key={location.id}
            className="absolute transform -translate-x-1/2 -translate-y-1/2"
            style={{
              left: `${30 + index * 15}%`,
              top: `${40 + (index % 2) * 20}%`,
            }}
          >
            <div className="relative group">
              <div className={`w-8 h-8 rounded-full ${getRiskColor(location.riskLevel)} flex items-center justify-center text-white shadow-lg cursor-pointer hover:scale-110 transition-transform`}>
                {getLocationIcon(location.type)}
              </div>

              {/* Tooltip */}
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                <div className="bg-gray-900 text-white text-sm rounded-lg px-3 py-2 whitespace-nowrap">
                  <div className="font-medium">{location.name}</div>
                  <div className="text-xs opacity-80">Risk: {location.riskLevel}</div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="grid grid-cols-3 gap-4">
        <div className="flex items-center gap-3 p-3 bg-blue-50 rounded-lg">
          <MapPin className="text-blue-600" size={20} />
          <div>
            <div className="font-medium text-gray-900 text-sm">Facilities</div>
            <div className="text-xs text-gray-600">{locations.filter(l => l.type === 'facility').length} locations</div>
          </div>
        </div>

        <div className="flex items-center gap-3 p-3 bg-green-50 rounded-lg">
          <Shield className="text-green-600" size={20} />
          <div>
            <div className="font-medium text-gray-900 text-sm">Protected Areas</div>
            <div className="text-xs text-gray-600">{locations.filter(l => l.type === 'protected').length} overlaps</div>
          </div>
        </div>

        <div className="flex items-center gap-3 p-3 bg-purple-50 rounded-lg">
          <Leaf className="text-purple-600" size={20} />
          <div>
            <div className="font-medium text-gray-900 text-sm">Species Records</div>
            <div className="text-xs text-gray-600">{locations.filter(l => l.type === 'species').length} sightings</div>
          </div>
        </div>
      </div>
    </div>
  );
}
