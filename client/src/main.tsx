import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";
import { createRoot } from "react-dom/client";
import { PlayApp } from "./App";
import { DsApp } from "./ds/DsApp";

const root = createRoot(document.getElementById("root")!);
root.render(location.pathname.startsWith("/ds") ? <DsApp /> : <PlayApp />);
