jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("@/lib/overpassBrowser", () => ({ fetchOverpass: jest.fn() }));
import { api } from "@/lib/api";
import { fetchOverpass } from "@/lib/overpassBrowser";
import { mapApi } from "@/lib/outreach";

const AREA = { south: 1, west: 2, north: 3, east: 4, category: "restaurants" };
const reply = (data) => Promise.resolve({ data });
beforeEach(() => jest.clearAllMocks());

test("the browser fetches Overpass and the server parses the answer", async () => {
  api.post.mockImplementation((url) => (url === "/map/query" ? reply({ query: "Q", endpoints: ["https://x.example/i"] }) : reply({ places: [{ name: "A" }] })));
  fetchOverpass.mockResolvedValue({ elements: [{ id: 1 }] });
  expect(await mapApi.find(AREA)).toEqual({ places: [{ name: "A" }] });
  expect(fetchOverpass).toHaveBeenCalledWith("Q", ["https://x.example/i"]);
  expect(api.post).toHaveBeenCalledWith("/map/parse", { data: { elements: [{ id: 1 }] } });
});

test("when the browser cannot reach any server, the server's own search is the fallback", async () => {
  api.post.mockImplementation((url) => (url === "/map/query" ? reply({ query: "Q", endpoints: ["https://x.example/i"] }) : reply({ places: [] })));
  fetchOverpass.mockRejectedValue(new Error("Browser could not reach OpenStreetMap servers (x.example: timeout)"));
  expect(await mapApi.find(AREA)).toEqual({ places: [] });
  expect(api.post).toHaveBeenCalledWith("/map/search", AREA);
});

test("if both fail, the message names the browser and the server causes", async () => {
  const serverError = Object.assign(new Error("502"), { response: { status: 502, data: { detail: "OpenStreetMap servers are busy (a: TimeoutError)" } } });
  api.post.mockImplementation((url) => (url === "/map/query" ? reply({ query: "Q", endpoints: [] }) : Promise.reject(serverError)));
  fetchOverpass.mockRejectedValue(new Error("Browser could not reach OpenStreetMap servers (x.example: timeout)"));
  await expect(mapApi.find(AREA)).rejects.toBe(serverError);
  expect(serverError.response.data.detail).toContain("x.example: timeout");
  expect(serverError.response.data.detail).toContain("a: TimeoutError");
});

test("a refusal of the parse step is shown as such, without a second try", async () => {
  const refused = Object.assign(new Error("422"), { response: { status: 422, data: { detail: "too large" } } });
  api.post.mockImplementation((url) => (url === "/map/query" ? reply({ query: "Q", endpoints: [] }) : Promise.reject(refused)));
  fetchOverpass.mockResolvedValue({ elements: [] });
  await expect(mapApi.find(AREA)).rejects.toBe(refused);
  expect(api.post).not.toHaveBeenCalledWith("/map/search", AREA);
});
