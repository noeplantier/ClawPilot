import { formatCoord, formatZoom, searchState } from "@/lib/mapHud";

test("coordinates are read with their hemisphere, to four decimals", () => {
  expect(formatCoord(45.764, 4.8357)).toBe("45.7640° N  4.8357° E");
  expect(formatCoord(-33.8688, -70.6693)).toBe("33.8688° S  70.6693° W");
  expect(formatCoord(0, 0)).toBe("0.0000° N  0.0000° E");
});

test("the zoom shows half levels, which the map allows (zoomSnap 0.5)", () => {
  expect(formatZoom(14)).toBe("Z14");
  expect(formatZoom(14.5)).toBe("Z14.5");
});

test("the search state follows what the map really does", () => {
  expect(searchState({ busy: true, tooLarge: true }).key).toBe("scanning"); // a running search wins
  expect(searchState({ busy: false, tooLarge: true })).toEqual({ key: "zoom", label: "ZOOM IN TO SEARCH" });
  expect(searchState({ busy: false, tooLarge: false }).key).toBe("ready");
});
