'use client';

import { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react';
import { CheckCircle2, XCircle, Info, AlertTriangle, X } from 'lucide-react';

type ToastType = 'success' | 'error' | 'info' | 'warning';

interface ToastItem {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
}

interface ToastContextValue {
  toast: (opts: Omit<ToastItem, 'id'>) => void;
  success: (title: string, message?: string) => void;
  error: (title: string, message?: string) => void;
  info: (title: string, message?: string) => void;
  warning: (title: string, message?: string) => void;
}

const noop = () => {};
const fallback: ToastContextValue = {
  toast: noop, success: noop, error: noop, info: noop, warning: noop,
};

const ToastContext = createContext<ToastContextValue>(fallback);

const ICONS: Record<ToastType, React.ElementType> = {
  success: CheckCircle2,
  error:   XCircle,
  info:    Info,
  warning: AlertTriangle,
};

const COLORS: Record<ToastType, string> = {
  success: '#00D4AA',
  error:   '#FF7B72',
  info:    '#58A6FF',
  warning: '#F0B90B',
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const remove = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
    const t = timers.current.get(id);
    if (t) { clearTimeout(t); timers.current.delete(id); }
  }, []);

  const toast = useCallback((opts: Omit<ToastItem, 'id'>) => {
    const id = Math.random().toString(36).slice(2);
    const duration = opts.duration ?? 4000;
    setToasts(prev => [...prev.slice(-4), { ...opts, id }]);
    const t = setTimeout(() => remove(id), duration);
    timers.current.set(id, t);
  }, [remove]);

  const success = useCallback((title: string, message?: string) => toast({ type: 'success', title, message }), [toast]);
  const error   = useCallback((title: string, message?: string) => toast({ type: 'error',   title, message }), [toast]);
  const info    = useCallback((title: string, message?: string) => toast({ type: 'info',    title, message }), [toast]);
  const warning = useCallback((title: string, message?: string) => toast({ type: 'warning', title, message }), [toast]);

  return (
    <ToastContext.Provider value={{ toast, success, error, info, warning }}>
      {children}
      <div className="toast-container">
        {toasts.map(t => {
          const Icon = ICONS[t.type];
          return (
            <div key={t.id} className={`toast ${t.type} animate-fade-up`}>
              <Icon size={16} style={{ color: COLORS[t.type], flexShrink: 0, marginTop: 1 }} />
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-[13px]" style={{ color: 'var(--text-main)' }}>{t.title}</div>
                {t.message && (
                  <div className="text-[12px] mt-0.5" style={{ color: 'var(--text-muted)' }}>{t.message}</div>
                )}
              </div>
              <button onClick={() => remove(t.id)} className="shrink-0 opacity-50 hover:opacity-100 transition-opacity">
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  return useContext(ToastContext);
}
