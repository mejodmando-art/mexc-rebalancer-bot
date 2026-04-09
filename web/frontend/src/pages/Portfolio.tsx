import { useEffect, useState } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { RefreshCw, DollarSign, Target, TrendingUp, AlertTriangle } from "lucide-react";
import { api } from "../api";
import type { PortfolioData } from "../api";
import StatCard from "../components/StatCard";
import Spinner from "../components/Spinner";
import toast from "react-hot-toast";

const COLORS = [
  "#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6",
  "#06b6d4", "#f97316", "#ec4899", "#14b8a6", "#a855f7",
  "#84cc16", "#0ea5e9", "#fb923c", "#e879f9", "#2dd4bf",
];

export default function Portfolio() {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await api.getPortfolio();
      setData(res.data);
    } catch (e: unknown) {
      const msg = (e as any)?.response?.data?.detail || "فشل تحميل المحفظة";
      toast.error(msg);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center space-y-3">
          <Spinner size={40} />
          <p className="text-slate-400 text-sm">جاري جلب بيانات المحفظة...</p>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const pieData = data.assets
    .filter(a => a.value_usdt > 0)
    .map((a, i) => ({
      name: a.symbol,
      value: parseFloat(a.value_usdt.toFixed(2)),
      color: COLORS[i % COLORS.length],
    }));

  const alertCount = data.assets.filter(a => a.needs_action).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">{data.portfolio_name}</h1>
          <p className="text-slate-400 text-sm mt-1">نظرة عامة على محفظتك</p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing}
          className="btn-secondary flex items-center gap-2"
        >
          <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
          تحديث
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="إجمالي الحساب"
          value={`$${data.total_usdt.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          icon={<DollarSign size={18} className="text-green-400" />}
          color="green"
        />
        {data.capital_usdt > 0 && (
          <StatCard
            label="رأس المال المخصص"
            value={`$${data.capital_usdt.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            icon={<Target size={18} className="text-blue-400" />}
            color="blue"
          />
        )}
        <StatCard
          label="عدد الأصول"
          value={`${data.assets.length}`}
          sub="أصل في المحفظة"
          icon={<TrendingUp size={18} className="text-yellow-400" />}
          color="yellow"
        />
        <StatCard
          label="تحتاج إعادة توازن"
          value={`${alertCount}`}
          sub={alertCount > 0 ? "أصل خارج النطاق" : "المحفظة متوازنة ✓"}
          icon={<AlertTriangle size={18} className={alertCount > 0 ? "text-red-400" : "text-green-400"} />}
          color={alertCount > 0 ? "red" : "green"}
        />
      </div>

      {/* Chart + Table */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pie Chart */}
        <div className="card">
          <h2 className="text-base font-semibold text-white mb-4">توزيع المحفظة</h2>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={70}
                outerRadius={110}
                paddingAngle={2}
                dataKey="value"
              >
                {pieData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} stroke="transparent" />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: "#0f1629", border: "1px solid #2e3d60", borderRadius: 12 }}
                formatter={((v: number) => [`$${Number(v).toFixed(2)}`, ""]) as any}
                labelStyle={{ color: "#e2e8f0" }}
              />
              <Legend
                formatter={(value) => <span style={{ color: "#94a3b8", fontSize: 12 }}>{value}</span>}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Assets Table */}
        <div className="card overflow-hidden">
          <h2 className="text-base font-semibold text-white mb-4">الأصول</h2>
          <div className="overflow-y-auto max-h-72 space-y-2">
            {data.assets.map((asset, i) => (
              <div
                key={asset.symbol}
                className={`flex items-center justify-between p-3 rounded-xl ${
                  asset.needs_action ? "bg-red-500/5 border border-red-500/20" : "bg-dark-700"
                }`}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ background: COLORS[i % COLORS.length] }}
                  />
                  <div>
                    <p className="font-semibold text-white text-sm">{asset.symbol}</p>
                    <p className="text-xs text-slate-500">
                      {asset.price > 0 ? `$${asset.price.toLocaleString("en", { maximumFractionDigits: 4 })}` : "—"}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-white text-sm">
                    ${asset.value_usdt.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </p>
                  <div className="flex items-center gap-1 justify-end mt-0.5">
                    <span className="text-xs text-slate-400">{asset.current_pct.toFixed(1)}%</span>
                    {asset.target_pct !== null && (
                      <>
                        <span className="text-xs text-slate-600">→</span>
                        <span className="text-xs text-slate-500">{asset.target_pct}%</span>
                        {asset.drift_pct !== null && Math.abs(asset.drift_pct) >= 0.5 && (
                          <span className={`text-xs font-medium ${asset.drift_pct > 0 ? "text-red-400" : "text-green-400"}`}>
                            ({asset.drift_pct > 0 ? "+" : ""}{asset.drift_pct.toFixed(1)}%)
                          </span>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Drift bars */}
      {data.assets.some(a => a.target_pct !== null) && (
        <div className="card">
          <h2 className="text-base font-semibold text-white mb-4">انحراف التوزيع</h2>
          <div className="space-y-3">
            {data.assets
              .filter(a => a.target_pct !== null)
              .sort((a, b) => Math.abs(b.drift_pct ?? 0) - Math.abs(a.drift_pct ?? 0))
              .map(asset => (
                <div key={asset.symbol} className="flex items-center gap-3">
                  <span className="text-sm font-medium text-slate-300 w-16 text-left flex-shrink-0">{asset.symbol}</span>
                  <div className="flex-1 bg-dark-700 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${asset.needs_action ? "bg-red-500" : "bg-brand-500"}`}
                      style={{ width: `${Math.min(100, asset.current_pct)}%` }}
                    />
                  </div>
                  <div className="flex items-center gap-2 w-28 flex-shrink-0 justify-end">
                    <span className="text-xs text-slate-400">{asset.current_pct.toFixed(1)}%</span>
                    {asset.drift_pct !== null && (
                      <span className={`text-xs font-medium ${asset.needs_action ? "text-red-400" : "text-slate-500"}`}>
                        {asset.drift_pct > 0 ? "+" : ""}{asset.drift_pct.toFixed(1)}%
                      </span>
                    )}
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
