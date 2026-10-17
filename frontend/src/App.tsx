import { Layout } from "./components/Layout";
import { useStore } from "./lib/store";
import { BenchmarksPage } from "./pages/Benchmarks";
import { BuildPage } from "./pages/Build";
import { ComparePage } from "./pages/Compare";
import { ExportPage } from "./pages/Export";
import { OverviewPage } from "./pages/Overview";
import { RepositoryPage } from "./pages/Repository";
import { ResultsPage } from "./pages/Results";

export default function App() {
  const { page } = useStore();
  return (
    <Layout>
      {page === "overview" && <OverviewPage />}
      {page === "repository" && <RepositoryPage />}
      {page === "build" && <BuildPage />}
      {page === "results" && <ResultsPage />}
      {page === "compare" && <ComparePage />}
      {page === "benchmarks" && <BenchmarksPage />}
      {page === "export" && <ExportPage />}
    </Layout>
  );
}
