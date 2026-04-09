import { useState } from "react";
import { Toaster } from "react-hot-toast";
import Sidebar from "./components/Sidebar";
import Portfolio from "./pages/Portfolio";
import Rebalance from "./pages/Rebalance";
import History from "./pages/History";
import Settings from "./pages/Settings";

export default function App() {
  const [page, setPage] = useState("portfolio");

  const pages: Record<string, React.ReactNode> = {
    portfolio: <Portfolio onNavigate={setPage} />,
    rebalance: <Rebalance onNavigate={setPage} />,
    history:   <History />,
    settings:  <Settings onNavigate={setPage} />,
  };

  return (
    <div className="flex min-h-screen bg-dark-900">
      <Toaster
        position="top-center"
        toastOptions={{
          style: {
            background: "#0f1629",
            color: "#e2e8f0",
            border: "1px solid #2e3d60",
            borderRadius: "12px",
            fontSize: "14px",
            direction: "rtl",
          },
          success: { iconTheme: { primary: "#22c55e", secondary: "#0f1629" } },
          error:   { iconTheme: { primary: "#ef4444", secondary: "#0f1629" } },
        }}
      />
      <Sidebar active={page} onChange={setPage} />
      <main className="flex-1 p-8 overflow-y-auto">
        <div className="max-w-5xl mx-auto">
          {pages[page]}
        </div>
      </main>
    </div>
  );
}
