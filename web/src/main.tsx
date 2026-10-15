import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/base.css";
import "./components/components.css";
import "./App.css";
import "./TryPage.css";
import { App } from "./App";
import { TryPage } from "./TryPage";

// Two pages for now; a router library arrives only if a third page needs one.
const Page = window.location.pathname.replace(/\/$/, "") === "/try" ? TryPage : App;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Page />
  </StrictMode>,
);
