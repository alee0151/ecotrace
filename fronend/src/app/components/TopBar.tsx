import { Search, Bell, HelpCircle, Command } from 'lucide-react';

export function TopBar({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="sticky top-0 z-20 bg-white/80 backdrop-blur-md border-b border-stone-200">
      <div className="px-8 py-4 flex items-center gap-6">
        <div className="min-w-0">
          <div className="text-[18px] text-stone-900 leading-tight">{title}</div>
          {subtitle && <div className="text-[12px] text-stone-500 leading-tight">{subtitle}</div>}
        </div>
        <div className="flex-1 max-w-xl mx-auto relative">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-stone-400" />
          <input
            placeholder="Search a barcode, brand, company or ABN…"
            className="w-full h-10 pl-10 pr-14 rounded-lg bg-stone-50 border border-stone-200 text-sm text-stone-800 placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-emerald-200 focus:border-emerald-400"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1 text-[10px] text-stone-400 border border-stone-200 rounded px-1.5 py-0.5">
            <Command size={10} /> K
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button className="w-9 h-9 rounded-lg hover:bg-stone-100 flex items-center justify-center text-stone-500">
            <HelpCircle size={16} />
          </button>
          <button className="w-9 h-9 rounded-lg hover:bg-stone-100 flex items-center justify-center text-stone-500 relative">
            <Bell size={16} />
            <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-emerald-500 ring-2 ring-white" />
          </button>
        </div>
      </div>
    </div>
  );
}
