interface Props {
  label: string;
  value: string;
  sub?: string;
  icon?: React.ReactNode;
  color?: "green" | "blue" | "yellow" | "red" | "default";
}

const colorMap = {
  green: "text-green-400",
  blue: "text-blue-400",
  yellow: "text-yellow-400",
  red: "text-red-400",
  default: "text-white",
};

export default function StatCard({ label, value, sub, icon, color = "default" }: Props) {
  return (
    <div className="card flex items-start gap-4">
      {icon && (
        <div className="w-10 h-10 bg-dark-700 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5">
          {icon}
        </div>
      )}
      <div className="min-w-0">
        <p className="text-xs text-slate-500 mb-1">{label}</p>
        <p className={`text-xl font-bold ${colorMap[color]} truncate`}>{value}</p>
        {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}
