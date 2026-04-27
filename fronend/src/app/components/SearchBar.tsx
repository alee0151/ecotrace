import { Search, ScanBarcode } from 'lucide-react';
import { useState } from 'react';

interface SearchBarProps {
  onSearch: (query: string, type: 'barcode' | 'brand' | 'company') => void;
}

export function SearchBar({ onSearch }: SearchBarProps) {
  const [query, setQuery] = useState('');
  const [searchType, setSearchType] = useState<'brand' | 'company'>('brand');
  const [showScanner, setShowScanner] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      onSearch(query, searchType);
    }
  };

  const handleScan = () => {
    setShowScanner(true);
    // Simulate barcode scan after 1.5s
    setTimeout(() => {
      onSearch('9310072001234', 'barcode');
      setShowScanner(false);
    }, 1500);
  };

  return (
    <div className="w-full max-w-3xl">
      <div className="flex gap-3 mb-4">
        <button
          onClick={() => setSearchType('brand')}
          className={`px-4 py-2 rounded-lg transition-colors ${
            searchType === 'brand'
              ? 'bg-emerald-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          Brand Name
        </button>
        <button
          onClick={() => setSearchType('company')}
          className={`px-4 py-2 rounded-lg transition-colors ${
            searchType === 'company'
              ? 'bg-emerald-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          Company Name
        </button>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="flex-1 relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" size={20} />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search by ${searchType}...`}
            className="w-full pl-12 pr-4 py-4 rounded-xl border-2 border-gray-200 focus:border-emerald-500 focus:outline-none text-lg"
          />
        </div>
        <button
          type="button"
          onClick={handleScan}
          className="px-6 py-4 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl flex items-center gap-2 transition-colors"
        >
          <ScanBarcode size={20} />
          Scan
        </button>
      </form>

      {showScanner && (
        <div className="mt-4 p-8 bg-gray-900 rounded-xl text-center">
          <div className="inline-block animate-pulse">
            <ScanBarcode className="text-emerald-400 mx-auto mb-3" size={48} />
            <p className="text-white">Scanning barcode...</p>
          </div>
        </div>
      )}
    </div>
  );
}
