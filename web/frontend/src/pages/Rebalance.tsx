import { useState } from "react";
import { RefreshCw, TrendingUp, TrendingDown, CheckCircle, AlertTriangle, Zap, Key } from "lucide-react";
import { api } from "../api";
import type { AnalysisData } from "../api";
import Spinner from "../components/Spinner";
import toast from "react-hot-toast";

export default function Rebalance({ onNavigate }: { onNavigate?: (p: string) => void }) {
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [done, setDone] = useState<any>(null);
  const [noKeys, setNoKeys] = useState(false);
  const [noAllocs, setNoAllocs] = useState(false);

  const analyze = async () => {
    setAnalyzing(true);
    setDone(null);
    setNoKeys(false);
    setNoAllocs(false);
    try {
      const res = await api.analyzeRebalance();
      setAnalysis(res.data);
    } catch (e: unknown) {
      const detail = (e as any)?.response?.data?.detail || "";
      if (detail.includes("API keys not configured") || detail.includes("مفاتيح")) {
        setNoKeys(true);
      } else if (detail.includes("No allocations") || detail.includes("توزيع")) {
        setNoAllocs(true);
      } else {
        toast.error(detail || "فشل التحليل");
      }
    } finally {
      setAnalyzing(false);
    }
  };

  const execute = async () => {
    if (!window.confirm("هل أنت متأكد من تنفيذ إعادة التوازن؟")) return;
    setExecuting(true);
    try {
      const res = await api.executeRebalance();
      setDone(res.data);
      setAnalysis(null);
      toast.success(`تم التنفيذ: ${res.data.ok} صفقة ناجحة`);
    } catch (e: unknown) {
      toast.error((e as any)?.response?.data?.detail || "فشل التنفيذ");
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">إعادة التوازن</h1>
        <p className="text-slate-400 text-sm mt-1">تحليل وتنفيذ إعادة توازن المحفظة</p>
      </div>

      {/* Analyze trigger */}
      <div className="card flex items-center justify-between gap-4">
        <div>
          <p className="font-semibold text-white">تحليل المحفظة</p>
          <p className="text-sm text-slate-400 mt-0.5">يقارن التوزيع الحالي بالأهداف ويحسب الصفقات اللازمة</p>
        </div>
        <button onClick={analyze} disabled={analyzing} className="btn-primary flex items-center gap-2 flex-shrink-0">
          {analyzing ? <Spinner size={16} /> : <RefreshCw size={16} />}
          {analyzing ? "جاري التحليل..." : "تحليل الآن"}
        </button>
      </div>

      {/* No API keys */}
      {noKeys && (
        <div className="card flex items-center gap-4">
          <div className="w-12 h-12 bg-blue-500/10 rounded-xl flex items-center justify-center flex-shrink-0">
            <Key size={22} className="text-blue-400" />
          </div>
          <div className="flex-1">
            <p className="font-semibold text-white">لم يتم ربط MEXC API</p>
            <p className="text-sm text-slate-400 mt-0.5">أضف مفاتيح API أولاً من صفحة الإعدادات</p>
          </div>
          <button onClick={() => onNavigate?.("settings")} className="btn-primary flex-shrink-0">الإعدادات</button>
        </div>
      )}

      {/* No allocations */}
      {noAllocs && (
        <div className="card flex items-center gap-4">
          <div className="w-12 h-12 bg-yellow-500/10 rounded-xl flex items-center justify-center flex-shrink-0">
            <AlertTriangle size={22} className="text-yellow-400" />
          </div>
          <div className="flex-1">
            <p className="font-semibold text-white">لا يوجد توزيع محدد</p>
            <p className="text-sm text-slate-400 mt-0.5">حدد توزيع المحفظة أولاً من صفحة الإعدادات</p>
          </div>
          <button onClick={() => onNavigate?.("settings")} className="btn-primary flex-shrink-0">الإعدادات</button>
        </div>
      )}

      {/* Analysis result */}
      {analysis && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="card text-center">
              <p className="text-xs text-slate-500 mb-1">قيمة المحفظة</p>
              <p className="text-lg font-bold text-white">${analysis.effective_total.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
            </div>
            <div className="card text-center">
              <p className="text-xs text-slate-500 mb-1">حد الانحراف</p>
              <p className="text-lg font-bold text-yellow-400">{analysis.threshold}%</p>
            </div>
            <div className="card text-center">
              <p className="text-xs text-slate-500 mb-1">مجموع التوزيع</p>
              <p className={`text-lg font-bold ${Math.abs(analysis.allocations_sum - 100) < 1 ? "text-green-400" : "text-red-400"}`}>{analysis.allocations_sum.toFixed(1)}%</p>
            </div>
            <div className="card text-center">
              <p className="text-xs text-slate-500 mb-1">صفقات مطلوبة</p>
              <p className={`text-lg font-bold ${analysis.trades.length > 0 ? "text-red-400" : "text-green-400"}`}>{analysis.trades.length}</p>
            </div>
          </div>

          <div className="card">
            <h2 className="text-base font-semibold text-white mb-4">تقرير الانحراف</h2>
            <div className="space-y-2">
              {analysis.drift_report.map(item => (
                <div key={item.symbol} className={`flex items-center justify-between p-3 rounded-xl ${item.needs_action ? "bg-red-500/5 border border-red-500/20" : "bg-dark-700"}`}>
                  <div className="flex items-center gap-3">
                    {item.needs_action
                      ? item.drift_pct > 0 ? <TrendingDown size={16} className="text-red-400" /> : <TrendingUp size={16} className="text-green-400" />
                      : <CheckCircle size={16} className="text-green-500" />
                    }
                    <span className="font-semibold text-white text-sm">{item.symbol}</span>
                  </div>
                  <div className="flex items-center gap-4 text-sm">
                    <span className="text-slate-400">{item.current_pct.toFixed(1)}%</span>
                    <span className="text-slate-600">→</span>
                    <span className="text-slate-300">{item.target_pct.toFixed(1)}%</span>
                    <span className={`font-semibold w-16 text-right ${item.needs_action ? (item.drift_pct > 0 ? "text-red-400" : "text-green-400") : "text-slate-500"}`}>
                      {item.drift_pct > 0 ? "+" : ""}{item.drift_pct.toFixed(1)}%
                    </span>
                    {item.needs_action && (
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${item.drift_pct > 0 ? "bg-red-500/20 text-red-400" : "bg-green-500/20 text-green-400"}`}>
                        {item.drift_pct > 0 ? "بيع" : "شراء"}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {analysis.trades.length > 0 ? (
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-base font-semibold text-white">الصفقات المطلوبة</h2>
                <span className="text-sm text-slate-400">إجمالي: ${analysis.trades.reduce((s, t) => s + t.usdt_amount, 0).toFixed(2)}</span>
              </div>
              <div className="space-y-2 mb-6">
                {analysis.trades.map(trade => (
                  <div key={trade.symbol} className="flex items-center justify-between p-3 bg-dark-700 rounded-xl">
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${trade.action === "sell" ? "bg-red-500/10" : "bg-green-500/10"}`}>
                        {trade.action === "sell" ? <TrendingDown size={16} className="text-red-400" /> : <TrendingUp size={16} className="text-green-400" />}
                      </div>
                      <div>
                        <p className="font-semibold text-white text-sm">{trade.symbol}</p>
                        <p className={`text-xs ${trade.action === "sell" ? "text-red-400" : "text-green-400"}`}>{trade.action === "sell" ? "بيع" : "شراء"}</p>
                      </div>
                    </div>
                    <p className="font-bold text-white">${trade.usdt_amount.toFixed(2)}</p>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-3 p-4 bg-yellow-500/5 border border-yellow-500/20 rounded-xl mb-4">
                <AlertTriangle size={18} className="text-yellow-400 flex-shrink-0" />
                <p className="text-sm text-yellow-300">سيتم تنفيذ الصفقات بأسعار السوق الحالية. تأكد من صحة الإعدادات قبل المتابعة.</p>
              </div>
              <button onClick={execute} disabled={executing} className="btn-primary w-full flex items-center justify-center gap-2">
                {executing ? <Spinner size={16} /> : <Zap size={16} />}
                {executing ? "جاري التنفيذ..." : "تنفيذ إعادة التوازن"}
              </button>
            </div>
          ) : (
            <div className="card flex items-center gap-4">
              <div className="w-12 h-12 bg-green-500/10 rounded-xl flex items-center justify-center flex-shrink-0">
                <CheckCircle size={24} className="text-green-400" />
              </div>
              <div>
                <p className="font-semibold text-white">المحفظة متوازنة</p>
                <p className="text-sm text-slate-400 mt-0.5">جميع الأصول ضمن حد الانحراف ({analysis.threshold}%)</p>
              </div>
            </div>
          )}
        </>
      )}

      {/* Execution result */}
      {done && (
        <div className="card">
          <h2 className="text-base font-semibold text-white mb-4">نتيجة التنفيذ</h2>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-green-400">{done.ok}</p>
              <p className="text-xs text-slate-400 mt-1">ناجح</p>
            </div>
            <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-red-400">{done.error}</p>
              <p className="text-xs text-slate-400 mt-1">خطأ</p>
            </div>
            <div className="bg-dark-700 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-white">${done.total_traded_usdt?.toFixed(2)}</p>
              <p className="text-xs text-slate-400 mt-1">إجمالي التداول</p>
            </div>
          </div>
          <div className="space-y-2">
            {done.results?.map((r: any, i: number) => (
              <div key={i} className="flex items-center justify-between p-3 bg-dark-700 rounded-xl text-sm">
                <div className="flex items-center gap-2">
                  <span>{r.status === "ok" ? "✅" : r.status === "error" ? "❌" : "⏭"}</span>
                  <span className="font-medium text-white">{r.symbol}</span>
                  <span className={`text-xs ${r.action === "sell" ? "text-red-400" : "text-green-400"}`}>{r.action === "sell" ? "بيع" : "شراء"}</span>
                </div>
                <span className="text-slate-400">{r.status === "ok" ? `$${r.usdt?.toFixed(2)}` : r.reason || ""}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
