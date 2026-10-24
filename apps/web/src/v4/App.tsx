// The v4 app (Gnomon Prototype v4, Release 1): its routes inside the shell. Each screen loads
// when first opened.

import { type ComponentType, lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";

import { ApiError } from "../api/client";
import { useMe } from "../api/hooks";
import { TalkProvider } from "../components/Talk";
import { Shell } from "./Shell";
import { Failure, Loading, Page } from "./ui";

function page<K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) {
  return lazy(() => load().then((module) => ({ default: module[name] })));
}

const HomePage = page(() => import("./pages/Home"), "HomePage");
const AskPage = page(() => import("./pages/Ask"), "AskPage");
const SearchPage = page(() => import("./pages/Search"), "SearchPage");
const SignInPage = page(() => import("./pages/SignIn"), "SignInPage");
const CapturePage = page(() => import("./pages/Capture"), "CapturePage");
const CaptureDetailPage = page(() => import("./pages/CaptureDetail"), "CaptureDetailPage");
const CatchUpPage = page(() => import("./pages/CatchUp"), "CatchUpPage");
const CardsPage = page(() => import("./pages/CatchUp"), "CardsPage");
const BrainPage = page(() => import("./pages/Brain"), "BrainPage");
const NotePage = page(() => import("./pages/Brain"), "NotePage");
const SheetPage = page(() => import("./pages/Brain"), "SheetPage");
const ProjectsPage = page(() => import("./pages/Projects"), "ProjectsPage");
const ProjectPage = page(() => import("./pages/Project"), "ProjectPage");
const AgentsPage = page(() => import("./pages/Agents"), "AgentsPage");
const ActivityPage = page(() => import("./pages/Activity"), "ActivityPage");
const SettingsPage = page(() => import("./pages/Settings"), "SettingsPage");
const StatesPage = page(() => import("./pages/States"), "StatesPage");

/** An address from the earlier app, kept working. */
function Moved({ to }: { to: string }) {
  const location = useLocation();
  return <Navigate to={`${to}${location.search}`} replace />;
}

export function V4Routes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/ask" element={<AskPage />} />
      <Route path="/search" element={<SearchPage />} />
      <Route path="/capture" element={<CapturePage />} />
      <Route path="/capture/:captureId" element={<CaptureDetailPage />} />
      <Route path="/brain" element={<BrainPage />} />
      <Route path="/brain/catch-up" element={<CatchUpPage />} />
      <Route path="/brain/cards" element={<CardsPage />} />
      <Route path="/brain/notes/:noteId" element={<NotePage />} />
      <Route path="/brain/sheets/:sheetId" element={<SheetPage />} />
      <Route path="/projects" element={<ProjectsPage />} />
      <Route path="/projects/:projectId" element={<ProjectPage />} />
      <Route path="/agents" element={<AgentsPage />} />
      <Route path="/activity" element={<ActivityPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/states" element={<StatesPage />} />
      <Route path="/catch-up" element={<Moved to="/brain/catch-up" />} />
      <Route path="/brain/entries/:noteId" element={<Moved to="/brain" />} />
      <Route path="/work/*" element={<Moved to="/agents" />} />
      <Route
        path="*"
        element={
          <Page>
            <Failure error={new Error("There's no page here. Use the menu to find what you were looking for.")} />
          </Page>
        }
      />
    </Routes>
  );
}

export function App() {
  const { isLoading, error } = useMe();
  if (isLoading) return <Loading />;
  if (error instanceof ApiError && error.status === 401)
    return (
      <Suspense fallback={<Loading />}>
        <SignInPage />
      </Suspense>
    );
  if (error) return <Failure error={error} />;
  return (
    <TalkProvider>
      <Shell>
        <Suspense fallback={<Loading />}>
          <V4Routes />
        </Suspense>
      </Shell>
    </TalkProvider>
  );
}
