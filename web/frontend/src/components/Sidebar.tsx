import { LayoutDashboard, RefreshCw, History, Settings, TrendingUp } from "lucide-react";

interface Props {
  active: string;
  onChange: (page: string) => void;
}

const nav = [
  { id: "portfolio", label: "المحفظة", icon: LayoutDashboard },
  { id: "rebalance", label: "إعادة التوازن", icon: RefreshCw },
  { id: "history", label: "السجل", icon: History },
  { id: "settings", label: "الإعدادات", icon: Settings },
];

export default function Sidebar({ active, onChange }: Props) {
  return (
    <aside className="w-64 min-h-screen bg-dark-800 border-l border-dark-600 flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-dark-600">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-brand-600 rounded-xl flex items-center justify-center">
            <TrendingUp size={20} className="text-white" />
          </div>
          <div>
            <p className="font-bold text-white text-sm">MEXC Rebalancer</p>
            <p className="text-xs text-slate-500">لوحة التحكم</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-4 space-y-1">
        {nav.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onChange(id)}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200 ${
              active === id
                ? "bg-brand-600/20 text-brand-400 border border-brand-600/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-dark-700"
            }`}
          >
            <Icon size={18} />
            {label}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-dark-600">
        <p className="text-xs text-slate-600 text-center">MEXC Rebalancer Bot v1.0</p>
      </div>
    </aside>
  );
}
