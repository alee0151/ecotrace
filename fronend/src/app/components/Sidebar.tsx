import { Leaf, Search, Building2, Map, GitBranch, TrendingUp, Star,Globe2 } from 'lucide-react';
import { useNavigate } from 'react-router';

export type PageId =
  | 'search'
  | 'overview'
  | 'analyse'
  | "spatial"
  | 'knowledge'
  | 'watchlist';

type NavItem = { id: PageId; label: string; icon: any; group: string };

const items: NavItem[] = [
  { id: 'search', label: 'Consumer Search', icon: Search, group: 'Consumer' },
  { id: 'overview', label: 'Company Overview', icon: Building2, group: 'Consumer' },
  { id: 'analyse', label: 'Analyse', icon: Map, group: 'Analysis' },
  { id: 'spatial', label: 'Spatial Analyse', icon: Globe2, group: 'Analysis'},
  { id: 'knowledge', label: 'Knowledge Graph', icon: GitBranch, group: 'Analysis' },
  { id: 'watchlist', label: 'Watchlist', icon: Star, group: 'Investor' },
];

export function Sidebar({ active }: { active: PageId }) {
  const navigate = useNavigate();
  const groups = Array.from(new Set(items.map(i => i.group)));
  return (
    <aside className="w-64 bg-white border-r border-stone-200 flex flex-col h-screen sticky top-0">
      <div className="px-5 py-5 border-b border-stone-200 flex items-center gap-2.5 cursor-pointer" onClick={() => navigate('/')}>
        <div className="p-2 bg-gradient-to-br from-emerald-500 to-emerald-700 rounded-lg">
          <Leaf className="text-white" size={20} />
        </div>
        <div>
          <div className="text-[15px] font-semibold text-stone-900 leading-tight">EcoTrace</div>
          <div className="text-[11px] text-stone-500 leading-tight">Biodiversity Intelligence</div>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {groups.map(group => (
          <div key={group} className="mb-5">
            <div className="px-3 text-[10px] tracking-wider uppercase text-stone-400 mb-1.5">{group}</div>
            {items.filter(i => i.group === group).map(item => {
              const Icon = item.icon;
              const isActive = active === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => navigate(`/app/${item.id}`)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all mb-0.5 ${
                    isActive
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'text-stone-600 hover:bg-stone-50 hover:text-stone-900'
                  }`}
                >
                  <Icon size={16} className={isActive ? 'text-emerald-600' : 'text-stone-400'} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
