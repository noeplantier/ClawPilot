import { act } from "react";
import { createRoot } from "react-dom/client";

import MapHud from "@/components/outreach/MapHud";

global.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;
beforeEach(() => { container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(() => { act(() => root.unmount()); container.remove(); });
const text = (id) => container.querySelector(`[data-testid="${id}"]`).textContent;
const mount = (props) => act(async () => root.render(<MapHud center={[45.764, 4.8357]} zoom={14} busy={false} tooLarge={false} {...props} />));

test("the readout is the map's own centre and zoom", async () => {
  await mount();
  expect(text("map-hud-coords")).toBe("45.7640° N  4.8357° E");
  expect(text("map-hud-zoom")).toBe("Z14");
  expect(text("map-hud-state")).toBe("AREA READY");
});

test("it says when the area is too large and when a search is running", async () => {
  await mount({ tooLarge: true });
  expect(text("map-hud-state")).toBe("ZOOM IN TO SEARCH");
  await mount({ busy: true, tooLarge: true });
  expect(text("map-hud-state")).toBe("SCANNING");
});
