import { PrismaPreviewPage } from "../workstation/pages/PrismaPreviewPage";

/** Shared financial Home: the preview and official route cannot drift. */
export function DashboardPage() {
  return <PrismaPreviewPage embedded />;
}
