'use client';

interface AssetRowProps {
  symbol: string;
  targetPct: number;
  actualPct: number;
  deviation: number;
  valueUsdt: number;
  balance: number;
  price: number;
}

export default function AssetRow({
  symbol, targetPct, actualPct, deviation, valueUsdt, balance, price,
}: AssetRowProps) {
  const isOver  = deviation > 0;
  const isUnder = deviation < 0;
  const absdev  = Math.abs(deviation);

  return (
    <tr className="border-b border-gray-800 hover:bg-gray-800/40 transition-colors">
      <td className="py-3 px-4">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-brand/20 flex items-center justify-center text-brand text-xs font-bold">
            {symbol.slice(0, 2)}
          </div>
          <span className="font-semibold text-white">{symbol}</span>
        </div>
      </td>
      <td className="py-3 px-4 text-gray-300">{targetPct.toFixed(1)}%</td>
      <td className="py-3 px-4">
        <div className="flex items-center gap-2">
          <div className="flex-1 bg-gray-800 rounded-full h-1.5 w-16">
            <div
              className="h-1.5 rounded-full bg-brand"
              style={{ width: `${Math.min(actualPct, 100)}%` }}
            />
          </div>
          <span className="text-white text-sm">{actualPct.toFixed(1)}%</span>
        </div>
      </td>
      <td className="py-3 px-4">
        <span className={`badge ${
          absdev < 1 ? 'bg-gray-800 text-gray-400' :
          isOver    ? 'bg-red-900/60 text-red-400' :
                      'bg-green-900/60 text-green-400'
        }`}>
          {isOver ? '+' : ''}{deviation.toFixed(1)}%
        </span>
      </td>
      <td className="py-3 px-4 text-gray-300">${valueUsdt.toFixed(2)}</td>
      <td className="py-3 px-4 text-gray-500 text-xs">
        {balance.toFixed(6)} @ ${price.toFixed(4)}
      </td>
    </tr>
  );
}
