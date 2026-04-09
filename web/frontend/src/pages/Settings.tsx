import { useEffect, useState } from "react";
import { Key, Target, DollarSign, PieChart, Plus, Trash2, CheckCircle, XCircle, Save } from "lucide-react";
import { api } from "../api";
import type { SettingsData, AllocationItem } from "../api";
import Spinner from "../components/Spinner";
import toast from "react-hot-toast";

export default function Settings() {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [loading, setLoading] = useState(true);

  const [apiKey, setApiKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [savingKeys, setSavingKeys] = useState(false);
  const [validating, setValidating] = useState(false);
  const [keyStatus, setKeyStatus] = useState<{ valid: boolean; message: string } | null>(null);

  const [threshold, setThreshold] = useState(5);
  const [savingThreshold, setSavingThreshold] = useState(false);

  const [capital, setCapital] = useState(0);
  const [savingCapital, setSavingCapital] = useState(false);

  const [allocs, setAllocs] = useState<AllocationItem[]>([]);
  const [savingAllocs, setSavingAllocs] = useState(false);
  const [newSymbol, setNewSymbol] = useState("");
  const [newPct, setNewPct] = useState("");

  const load = async () => {
    try {
      const res = await api.getSettings();
      const s = res.data;
      setSettings(s);
      setThreshold(s.threshold);
      setCapital(s.capital_usdt);
      setAllocs(s.allocations.map(a => ({ ...a })));
    } catch {
      toast.error("فشل تحميل الإعدادات");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const saveKeys = async () => {
    if (!apiKey || !secretKey) { toast.error("أدخل المفتاحين"); return; }
    setSavingKeys(true);
    try {
      await api.saveApiKeys(apiKey, secretKey);
      toast.success("تم حفظ المفاتيح والتحقق منها");
      setApiKey(""); setSecretKey("");
      load();
    } catch (e: unknown) {
      toast.error((e as any)?.response?.data?.detail || "فشل حفظ المفاتيح");
    } finally {
      setSavingKeys(false);
    }
  };

  const validateKeys = async () => {
    setValidating(true);
    setKeyStatus(null);
    try {
      const res = await api.validateKeys();
      setKeyStatus(res.data);
    } catch {
      setKeyStatus({ valid: false, message: "فشل التحقق" });
    } finally {
      setValidating(false);
    }
  };

  const saveThreshold = async () => {
    setSavingThreshold(true);
    try {
      await api.saveThreshold(threshold);
      toast.success("تم حفظ حد الانحراف");
    } catch (e: unknown) {
      toast.error((e as any)?.response?.data?.detail || "فشل الحفظ");
    } finally {
      setSavingThreshold(false);
    }
  };

  const saveCapital = async () => {
    setSavingCapital(true);
    try {
      await api.saveCapital(capital);
      toast.success("تم حفظ رأس المال");
    } catch (e: unknown) {
      toast.error((e as any)?.response?.data?.detail || "فشل الحفظ");
    } finally {
      setSavingCapital(false);
    }
  };

  const addAlloc = () => {
    const sym = newSymbol.trim().toUpperCase();
    const pct = parseFloat(newPct);
    if (!sym || isNaN(pct) || pct <= 0) { toast.error("أدخل رمز ونسبة صحيحة"); return; }
    if (allocs.find(a => a.symbol === sym)) { toast.error("الرمز موجود بالفعل"); return; }
    setAllocs([...allocs, { symbol: sym, target_percentage: pct }]);
    setNewSymbol(""); setNewPct("");
  };

  const removeAlloc = (sym: string) => setAllocs(allocs.filter(a => a.symbol !== sym));

  const updateAllocPct = (sym: string, val: string) => {
    setAllocs(allocs.map(a => a.symbol === sym ? { ...a, target_percentage: parseFloat(val) || 0 } : a));
  };

  const allocSum = allocs.reduce((s, a) => s + (a.target_percentage || 0), 0);

  const saveAllocs = async () => {
    if (Math.abs(allocSum - 100) > 1) { toast.error(`المجموع ${allocSum.toFixed(1)}% — يجب أن يكون 100%`); return; }
    setSavingAllocs(true);
    try {
      await api.saveAllocations(allocs);
      toast.success("تم حفظ التوزيع");
    } catch (e: unknown) {
      toast.error((e as any)?.response?.data?.detail || "فشل الحفظ");
    } finally {
      setSavingAllocs(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size={40} />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white">الإعدادات</h1>
        <p className="text-slate-400 text-sm mt-1">إدارة مفاتيح API والتوزيع والإعدادات العامة</p>
      </div>

      {/* API Keys */}
      <div className="card space-y-4">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-9 h-9 bg-blue-500/10 rounded-xl flex items-center justify-center">
            <Key size={18} className="text-blue-400" />
          </div>
          <div>
            <h2 className="font-semibold text-white">مفاتيح MEXC API</h2>
            {settings?.has_api_keys && (
              <p className="text-xs text-slate-500">مفعّل: {settings.api_key_preview}</p>
            )}
          </div>
          {settings?.has_api_keys && <span className="badge-green mr-auto">مفعّل</span>}
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-slate-400 mb-1.5 block">API Key</label>
            <input className="input font-mono text-sm" placeholder="أدخل API Key الجديد" value={apiKey} onChange={e => setApiKey(e.target.value)} dir="ltr" />
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1.5 block">Secret Key</label>
            <input className="input font-mono text-sm" type="password" placeholder="أدخل Secret Key الجديد" value={secretKey} onChange={e => setSecretKey(e.target.value)} dir="ltr" />
          </div>
        </div>
        <div className="flex gap-3">
          <button onClick={saveKeys} disabled={savingKeys} className="btn-primary flex items-center gap-2">
            {savingKeys ? <Spinner size={14} /> : <Save size={14} />}
            حفظ المفاتيح
          </button>
          {settings?.has_api_keys && (
            <button onClick={validateKeys} disabled={validating} className="btn-secondary flex items-center gap-2">
              {validating ? <Spinner size={14} /> : <CheckCircle size={14} />}
              التحقق
            </button>
          )}
        </div>
        {keyStatus && (
          <div className={`flex items-center gap-2 p-3 rounded-xl text-sm ${keyStatus.valid ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
            {keyStatus.valid ? <CheckCircle size={16} /> : <XCircle size={16} />}
            {keyStatus.message}
          </div>
        )}
      </div>

      {/* Threshold */}
      <div className="card space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-yellow-500/10 rounded-xl flex items-center justify-center">
            <Target size={18} className="text-yellow-400" />
          </div>
          <h2 className="font-semibold text-white">حد الانحراف</h2>
        </div>
        <p className="text-sm text-slate-400">يتم تنفيذ إعادة التوازن عندما ينحرف أصل عن هدفه بأكثر من هذه النسبة.</p>
        <div className="flex items-center gap-3">
          <input type="number" min="0.1" max="50" step="0.5" className="input w-32" value={threshold} onChange={e => setThreshold(parseFloat(e.target.value))} dir="ltr" />
          <span className="text-slate-400">%</span>
          <button onClick={saveThreshold} disabled={savingThreshold} className="btn-primary flex items-center gap-2">
            {savingThreshold ? <Spinner size={14} /> : <Save size={14} />}
            حفظ
          </button>
        </div>
      </div>

      {/* Capital */}
      <div className="card space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-green-500/10 rounded-xl flex items-center justify-center">
            <DollarSign size={18} className="text-green-400" />
          </div>
          <h2 className="font-semibold text-white">رأس المال المخصص</h2>
        </div>
        <p className="text-sm text-slate-400">حدد الحد الأقصى من رصيدك المخصص لهذه المحفظة. اتركه 0 لاستخدام كامل الرصيد.</p>
        <div className="flex items-center gap-3">
          <span className="text-slate-400">$</span>
          <input type="number" min="0" step="10" className="input w-40" value={capital} onChange={e => setCapital(parseFloat(e.target.value) || 0)} dir="ltr" />
          <span className="text-slate-400">USDT</span>
          <button onClick={saveCapital} disabled={savingCapital} className="btn-primary flex items-center gap-2">
            {savingCapital ? <Spinner size={14} /> : <Save size={14} />}
            حفظ
          </button>
        </div>
      </div>

      {/* Allocations */}
      <div className="card space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-purple-500/10 rounded-xl flex items-center justify-center">
              <PieChart size={18} className="text-purple-400" />
            </div>
            <h2 className="font-semibold text-white">توزيع المحفظة</h2>
          </div>
          <span className={`text-sm font-semibold ${Math.abs(allocSum - 100) < 1 ? "text-green-400" : "text-red-400"}`}>
            {allocSum.toFixed(1)}% / 100%
          </span>
        </div>
        <div className="space-y-2">
          {allocs.map(a => (
            <div key={a.symbol} className="flex items-center gap-3 p-3 bg-dark-700 rounded-xl">
              <span className="font-semibold text-white text-sm w-16">{a.symbol}</span>
              <input type="number" min="0.1" max="100" step="0.1" className="input w-24 text-sm py-1.5" value={a.target_percentage} onChange={e => updateAllocPct(a.symbol, e.target.value)} dir="ltr" />
              <span className="text-slate-400 text-sm">%</span>
              <div className="flex-1 bg-dark-600 rounded-full h-1.5 overflow-hidden">
                <div className="h-full bg-brand-500 rounded-full" style={{ width: `${Math.min(100, a.target_percentage)}%` }} />
              </div>
              <button onClick={() => removeAlloc(a.symbol)} className="text-slate-500 hover:text-red-400 transition-colors">
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2 p-3 bg-dark-700 rounded-xl">
          <input className="input w-24 text-sm py-1.5" placeholder="BTC" value={newSymbol} onChange={e => setNewSymbol(e.target.value.toUpperCase())} dir="ltr" />
          <input type="number" className="input w-24 text-sm py-1.5" placeholder="25" value={newPct} onChange={e => setNewPct(e.target.value)} dir="ltr" />
          <span className="text-slate-400 text-sm">%</span>
          <button onClick={addAlloc} className="btn-secondary flex items-center gap-1.5 py-1.5 text-sm">
            <Plus size={14} />
            إضافة
          </button>
        </div>
        <button onClick={saveAllocs} disabled={savingAllocs || Math.abs(allocSum - 100) > 1} className="btn-primary w-full flex items-center justify-center gap-2">
          {savingAllocs ? <Spinner size={14} /> : <Save size={14} />}
          حفظ التوزيع
        </button>
      </div>
    </div>
  );
}
