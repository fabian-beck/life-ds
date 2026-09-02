import "./report.css";
import { mount } from "svelte";
import Analysis from "./Analysis.svelte";

const app = mount(Analysis, {
  target: document.getElementById("analysis"),
});

export default app;
