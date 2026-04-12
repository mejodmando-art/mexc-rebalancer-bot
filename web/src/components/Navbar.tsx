'use client';

interface NavbarProps {
  active: 'dashboard' | 'create' | 'settings';
  onNav: (tab: 'dashboard' | 'create' | 'settings') => void;
  botRunning: boolean;
}

export default function Navbar({ active, onNav, botRunning }: NavbarProps) {
  return (
    <nav className="bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center justify-between sticky top-0 z-50">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-brand rounded-lg flex items-center justify-center text-black font-bold text-sm">SP</div>
        <span className="font-bold text-white text-lg">Smart Portfolio</span>
        <span className="text-xs text-gray-500 hidden sm:block">MEXC Spot</span>
      </div>

      <div className="flex items-center gap-1 bg-gray-800 rounded-xl p-1">
        <button
          onClick={() => onNav('dashboard')}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            active === 'dashboard' ? 'bg-brand text-black' : 'text-gray-400 hover:text-white'
          }`}
        >
          📊 لوحة التحكم
        </button>
        <button
          onClick={() => onNav('create')}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            active === 'create' ? 'bg-brand text-black' : 'text-gray-400 hover:text-white'
          }`}
        >
          ➕ إنشاء بوت
        </button>
        <button
          onClick={() => onNav('settings')}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            active === 'settings' ? 'bg-brand text-black' : 'text-gray-400 hover:text-white'
          }`}
        >
          ⚙️ الإعدادات
        </button>
      </div>

      <div className="flex items-center gap-2">
        <span className={`badge ${botRunning ? 'bg-green-900 text-green-400' : 'bg-gray-800 text-gray-500'}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${botRunning ? 'bg-green-400' : 'bg-gray-500'}`} />
          {botRunning ? 'شغال' : 'متوقف'}
        </span>
      </div>
    </nav>
  );
}
