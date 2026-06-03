import React from "react";
import ReactDOM from "react-dom/client";
import { HsapApp } from "./app/HsapApp";
import "./styles/index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <HsapApp />
  </React.StrictMode>,
);
