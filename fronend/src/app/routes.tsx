import { createBrowserRouter } from "react-router";
import { Landing } from "./pages/Landing";
import { Root } from "./Root";
import { ConsumerSearch } from "./pages/ConsumerSearch";
import { CompanyOverview } from "./pages/CompanyOverview";
import { Analyse } from "./pages/Analyse";
import { KnowledgeGraph } from "./pages/KnowledgeGraph";
import { Watchlist } from "./pages/Watchlist";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Landing,
  },
  {
    path: "/app",
    Component: Root,
    children: [
      { path: "search", Component: ConsumerSearch },
      { path: "overview", Component: CompanyOverview },
      { path: "analyse", Component: Analyse },
      { path: "knowledge", Component: KnowledgeGraph },
      { path: "watchlist", Component: Watchlist },
    ],
  },
]);