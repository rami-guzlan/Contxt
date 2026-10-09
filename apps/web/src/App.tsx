import { type ComponentType, lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router";

import { ApiError } from "./api/client";
import { useMe } from "./api/hooks";
import { Layout } from "./components/Layout";
import { TalkProvider } from "./components/Talk";
import { ErrorNote, Loading } from "./components/ui";
import { skillUrl } from "./lib/links";
import { HomePage } from "./pages/Home";
import { SignInPage } from "./pages/SignIn";

/** A page loaded when it is first opened, so the first screen does not wait for all of them. */
function page<K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) {
  return lazy(() => load().then((module) => ({ default: module[name] })));
}

const AiActivityPage = page(() => import("./pages/Activity"), "AiActivityPage");
const AgentPage = page(() => import("./pages/brain/Agent"), "AgentPage");
const BrainLayout = page(() => import("./pages/brain/BrainLayout"), "BrainLayout");
const KnowsPage = page(() => import("./pages/brain/Knows"), "KnowsPage");
const CatchUpPage = page(() => import("./pages/CatchUp"), "CatchUpPage");
const FirstRunPage = page(() => import("./pages/FirstRun"), "FirstRunPage");
const MoveInPage = page(() => import("./pages/MoveIn"), "MoveInPage");
const EntryPage = page(() => import("./pages/brain/Entry"), "EntryPage");
const FilesPage = page(() => import("./pages/brain/Files"), "FilesPage");
const FileViewPage = page(() => import("./pages/brain/Files"), "FileViewPage");
const GapsPage = page(() => import("./pages/brain/Gaps"), "GapsPage");
const InventoryPage = page(() => import("./pages/brain/Inventory"), "InventoryPage");
const CapturePage = page(() => import("./pages/Capture"), "CapturePage");
const NotePage = page(() => import("./pages/Notes"), "NotePage");
const ProjectPage = page(() => import("./pages/Projects"), "ProjectPage");
const ProjectsPage = page(() => import("./pages/Projects"), "ProjectsPage");
const ReviewPage = page(() => import("./pages/brain/Review"), "ReviewPage");
const SearchPage = page(() => import("./pages/Misc"), "SearchPage");
const SettingsPage = page(() => import("./pages/Settings"), "SettingsPage");
const WorkLayout = page(() => import("./pages/work/WorkLayout"), "WorkLayout");
const WorkOverviewPage = page(() => import("./pages/work/Overview"), "WorkOverviewPage");
const OutputsPage = page(() => import("./pages/work/Outputs"), "OutputsPage");
const SkillPage = page(() => import("./pages/work/Skills"), "SkillPage");
const SkillsPage = page(() => import("./pages/work/Skills"), "SkillsPage");

/** An old address that moved: same path below the moved part, same query. */
function Moved({ from, to }: { from: string; to: string }) {
  const location = useLocation();
  const rest = location.pathname.slice(from.length);
  return <Navigate to={`${to}${rest}${location.search}`} replace />;
}

/** A link to a retired page (goals, to-dos, tasks, meetings) goes home; a doc from the old Work
 * is a note in Capture now, under the same id. */
function Retired() {
  const { workId } = useParams();
  return <Navigate to={workId ? `/capture/${workId}` : "/"} replace />;
}

/** The Brain's history moved to Activity, Changes; its filters come along. */
function HistoryMoved() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  params.set("tab", "changes");
  return <Navigate to={`/activity?${params.toString()}`} replace />;
}

/** A skill's page from when skills were part of the Library's files. */
function SkillMoved() {
  const { name = "" } = useParams();
  return <Navigate to={skillUrl(name)} replace />;
}

export function App() {
  const { isLoading, error } = useMe();
  const location = useLocation();
  if (isLoading) return <Loading />;
  if (error instanceof ApiError && error.status === 401) return <SignInPage />;
  if (error) return <ErrorNote error={error} />;
  // The first run is full screen: no navigation, nothing else to look at.
  if (location.pathname.startsWith("/welcome")) {
    return (
      <TalkProvider>
        <Suspense fallback={<Loading />}>
          <FirstRunPage />
        </Suspense>
      </TalkProvider>
    );
  }
  return (
    <Layout>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/catch-up" element={<CatchUpPage />} />
          <Route path="/move-in" element={<MoveInPage />} />
          <Route path="/activity" element={<AiActivityPage />} />
          <Route path="/capture" element={<CapturePage />} />
          <Route path="/capture/:noteId" element={<NotePage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectPage />} />
          <Route path="/brain" element={<BrainLayout />}>
            <Route index element={<KnowsPage />} />
            <Route path="entries" element={<InventoryPage />} />
            <Route path="entries/:entryId" element={<EntryPage />} />
            <Route path="files" element={<FilesPage />} />
            <Route path="files/view" element={<FileViewPage />} />
            <Route path="questions" element={<GapsPage />} />
            <Route path="agent" element={<AgentPage />} />
          </Route>
          <Route path="/work" element={<WorkLayout />}>
            <Route index element={<WorkOverviewPage />} />
            <Route path="skills" element={<SkillsPage />} />
            <Route path="skills/:name" element={<SkillPage />} />
            <Route path="outputs" element={<OutputsPage />} />
            {/* A doc from the old Work, before it became Capture. */}
            <Route path=":workId" element={<Retired />} />
          </Route>
          <Route path="/brain/history" element={<HistoryMoved />} />
          <Route path="/brain/gaps" element={<Navigate to="/brain/questions" replace />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/search" element={<SearchPage />} />
          {/* Addresses from before: the Library and Activity became the Brain, Notes became
              Capture, Skills and Outputs moved into Work, and some pages went. */}
          <Route path="/skills/*" element={<Moved from="/skills" to="/work/skills" />} />
          <Route path="/outputs/*" element={<Moved from="/outputs" to="/work/outputs" />} />
          <Route path="/library/skills/:name" element={<SkillMoved />} />
          <Route path="/library/*" element={<Moved from="/library" to="/brain" />} />
          <Route path="/activity/gaps" element={<Navigate to="/brain/questions" replace />} />
          <Route path="/activity/policies" element={<Navigate to="/settings?tab=approval" replace />} />
          <Route path="/notes/*" element={<Moved from="/notes" to="/capture" />} />
          <Route path="/brain/review" element={<Navigate to="/review" replace />} />
          <Route path="/brain/activity" element={<Navigate to="/activity?tab=changes" replace />} />
          <Route path="/brain/policies" element={<Navigate to="/settings?tab=approval" replace />} />
          <Route path="/suggestions" element={<Navigate to="/review" replace />} />
          <Route path="/approvals" element={<Navigate to="/review" replace />} />
          <Route path="/connections" element={<Navigate to="/settings?tab=apps" replace />} />
          <Route path="/goals/*" element={<Retired />} />
          <Route path="/todos" element={<Retired />} />
          <Route path="/tasks/*" element={<Retired />} />
          <Route path="/meetings/*" element={<Retired />} />
          <Route path="/inspect" element={<Retired />} />
          <Route path="*" element={<p>Not found.</p>} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
