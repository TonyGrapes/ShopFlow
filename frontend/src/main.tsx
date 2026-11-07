import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./app/styles/tokens.css";
import "./app/styles/base.css";
import App from "./App.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
