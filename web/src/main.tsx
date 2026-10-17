import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/base.css";
import "./components/components.css";
import "./App.css";
import "./TryPage.css";
import "./Dashboard.css";
import "./Shell.css";
import { ComplaintPage } from "./ComplaintPage";
import { Shell } from "./Shell";
import { TryPage } from "./TryPage";

// The citizen pages (/try, /c/…) have no sidebar and load on their own. Every other address is the
// officer dashboard, whose pages switch without a reload (see lib/router.tsx).
const path = window.location.pathname.replace(/\/$/, "");
const complaintId = path.match(/^\/c\/([^/]+)$/)?.[1];
const page = complaintId ? <ComplaintPage trackingId={decodeURIComponent(complaintId)} /> : path === "/try" ? <TryPage /> : <Shell />;

createRoot(document.getElementById("root")!).render(<StrictMode>{page}</StrictMode>);
