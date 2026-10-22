import { AuthLayout, Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { useStore } from "./lib/store";
import { BenchmarksPage } from "./pages/Benchmarks";
import { BuildPage } from "./pages/Build";
import { ComparePage } from "./pages/Compare";
import { ConversationPage } from "./pages/Conversation";
import { ExportPage } from "./pages/Export";
import { LoginPage } from "./pages/Login";
import { OverviewPage } from "./pages/Overview";
import { RepositoryPage } from "./pages/Repository";
import { ResultsPage } from "./pages/Results";
import { SavedPage } from "./pages/Saved";

export default function App() {
  const { page, user, authChecked, apiStatus } = useStore();

  // Every visitor logs in first; each account works in its own private workspace.
  if (!user) {
    return (
      <AuthLayout>
        {authChecked || apiStatus === "offline" ? (
          apiStatus === "online" ? <LoginPage /> : null
        ) : (
          <div className="py-20 text-center"><Spinner label="Checking your session…" /></div>
        )}
      </AuthLayout>
    );
  }

  return (
    <Layout>
      {page === "overview" && <OverviewPage />}
      {page === "repository" && <RepositoryPage />}
      {page === "build" && <BuildPage />}
      {page === "results" && <ResultsPage />}
      {page === "compare" && <ComparePage />}
      {page === "benchmarks" && <BenchmarksPage />}
      {page === "conversation" && <ConversationPage />}
      {page === "export" && <ExportPage />}
      {page === "saved" && <SavedPage />}
    </Layout>
  );
}
