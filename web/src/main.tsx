import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { TimeZoneProvider } from "./state/timeZone";
import "./styles/global.css";

const container = document.getElementById("root");
if (!container) throw new Error("missing #root");

createRoot(container).render(
  <StrictMode>
    <TimeZoneProvider>
      <App />
    </TimeZoneProvider>
  </StrictMode>,
);
