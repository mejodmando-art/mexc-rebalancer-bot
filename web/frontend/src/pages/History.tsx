import { useEffect, useState } from "react";
import { RefreshCw, CheckCircle, XCircle, Clock, DollarSign } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api } from "../api";
import type { HistoryItem } from "../api";
import Spinner from "../components/Spinner";
import toast from "react-hot-toast";

export default function History() {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await api.getHistory(30);
      setHistory(res.data.history);
    } catch {
      toast.error("فشل تحميل السجل");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size={40} />
      </div>
    );
  }

  const totalTraded = history.reduce((s, h) => s + h.total_traded_usdt, 0);
  const successCount = history.filter(h => h.success).length;

  const chartData = [...history]
    .slice(0, 10)
    .reverse()
    .map(h => ({
      label: h.timestamp.slice(5, 16),
      amount: h.total_traded_usdt,
    }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">سجل العمليات</h1>
          <p className="text-slate-400 text-sm mt-1">آخر 30 عملية توازن</p>
        </div>
        <button onClick={() => load(true)} disabled={refreshing} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
          تحديث
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card text-center">
          <div className="w-10 h-10 bg-blue-500/10 rounded-xl flex items-center justify-center mx-auto mb-3">
            <Clock size={20} className="text-blue-400" />
          </div>
          <p className="text-2xl font-bold text-white">{history.length}</p>
          <p className="text-xs text-slate-500 mt-1">إجمالي العمليات</p>
        </div>
        <div className="card text-center">
          <div className="w-10 h-10 bg-green-500/10 rounded-xl flex items-center justify-center mx-auto mb-3">
            <CheckCircle size={20} className="text-green-400" />
          </div>
          <p className="text-2xl font-bold text-green-400">{successCount}</p>
          <p className="text-xs text-slate-500 mt-1">ناجحة</p>
        </div>
        <div className="card text-center">
          <div className="w-10 h-10 bg-brand-600/10 rounded-xl flex items-center justify-center mx-auto mb-3">
            <DollarSign size={20} className="text-brand-400" />
          </div>
          <p className="text-2xl font-bold text-brand-400">
            ${totalTraded.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <p className="text-xs text-slate-500 mt-1">إجمالي التداول</p>
        </div>
      </div>

      {/* Chart */}
      {chartData.length > 0 && (
        <div className="card">
          <h2 className="text-base font-semibold text-white mb-4">حجم التداول (آخر 10 عمليات)</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData} barSize={28}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1c2840" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `$${v}`} />
              <Tooltip
                contentStyle={{ background: "#0f1629", border: "1px solid #2e3d60", borderRadius: 12 }}
                formatter={((v: number) => [`$${Number(v).toFixed(2)}`, "حجم التداول"]) as any}
                labelStyle={{ color: "#94a3b8" }}
              />
              <Bar dataKey="amount" fill="#22c55e" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* List */}
      {history.length === 0 ? (
        <div className="card text-center py-12">
          <Clock size={40} className="text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">لا توجد عمليات مسجلة بعد</p>
          <p className="text-slate-600 text-sm mt-1">نفّذ أول عملية توازن لتظهر هنا</p>
        </div>
      ) : (
        <div className="card overflow-hidden p-0">
          <div className="p-4 border-b border-dark-600">
            <h2 className="text-base font-semibold text-white">العمليات</h2>
          </div>
          <div className="divide-y divide-dark-600">
            {history.map((h, i) => (
              <div key={i} className="flex items-center justify-between p-4 hover:bg-dark-700/50 transition-colors">
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                    h.success ? "bg-green-500/10" : "bg-red-500/10"
                  }`}>
                    {h.success
                      ? <CheckCircle size={16} className="text-green-400" />
                      : <XCircle size={16} className="text-red-400" />
                    }
                  </div>
                  <div>
                    <p className="text-sm font-medium text-white">{h.summary}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <p className="text-xs text-slate-500">{h.timestamp}</p>
                      {h.portfolio_name && (
                        <>
                          <span className="text-slate-700">·</span>
                          <p className="text-xs text-slate-500">{h.portfolio_name}</p>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="font-semibold text-white text-sm">
                    ${h.total_traded_usdt.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </p>
                  <span className={`text-xs ${h.success ? "text-green-400" : "text-red-400"}`}>
                    {h.success ? "ناجح" : "فشل"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
