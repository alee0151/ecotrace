import { createBrowserRouter, Navigate} from "react-router";
import { Landing } from "./pages/Landing";
import { Root } from "./Root";
import { ConsumerSearch } from "./pages/ConsumerSearch";
import { CompanyOverview } from "./pages/CompanyOverview";
import { Analyse } from "./pages/Analyse";
import { Watchlist } from "./pages/Watchlist";
import { SpatialAnalysisPage } from "./pages/spatial-analysis";
import { VerifyEmail } from "./pages/VerifyEmail";

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
      { path: "knowledge", element: <Navigate to="/app/analyse" replace /> },
      { path: "watchlist", Component: Watchlist },
      { path: "spatial", Component: SpatialAnalysisPage },
      { path: "verify-email", Component: VerifyEmail },
     ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
