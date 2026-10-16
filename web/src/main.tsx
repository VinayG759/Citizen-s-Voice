import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/base.css";
import "./components/components.css";
import "./App.css";
import "./TryPage.css";
import "./Dashboard.css";
import { App } from "./App";
import { ComplaintPage } from "./ComplaintPage";
import { TryPage } from "./TryPage";

// Three pages, matched by address. Still too few to need a router library.
const path = window.location.pathname.replace(/\/$/, "");
const complaintId = path.match(/^\/c\/([^/]+)$/)?.[1];
const page = complaintId ? <ComplaintPage trackingId={decodeURIComponent(complaintId)} /> : path === "/try" ? <TryPage /> : <App />;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {page}
  </StrictMode>,
);
