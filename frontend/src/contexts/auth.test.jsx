import { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));

import { api } from "@/lib/api";
import * as swr from "@/lib/swr";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";

global.IS_REACT_ACT_ENVIRONMENT = true;

const ME = { user: { id: "u1", email: "o@x.example", role: "owner" }, organization: { id: "o1", name: "Plantiers" } };
const CACHED = { user: { id: "u1", email: "cached@x.example", role: "owner" }, organization: { id: "o1", name: "Cached org" } };

let container;
let root;
let auth;
function Probe() {
  auth = useAuth();
  return null;
}
const mount = async () => {
  await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
};

beforeEach(() => {
  localStorage.clear();
  api.get.mockReset();
  api.post.mockReset();
  container = document.createElement("div");
  root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); });

test("a signed-in person who comes back is shown the app at once, from the cached identity, then the server's answer replaces it", async () => {
  localStorage.setItem("outreachos_token", "t");
  localStorage.setItem("outreachos_session", JSON.stringify(CACHED));
  let release;
  api.get.mockReturnValue(new Promise((r) => { release = r; })); // the API is still waking up
  await mount();
  expect(auth.loading).toBe(false); // no boot screen
  expect(auth.user.email).toBe("cached@x.example");
  expect(auth.org.name).toBe("Cached org");
  await act(async () => release({ data: ME }));
  expect(auth.user.email).toBe("o@x.example");
  expect(JSON.parse(localStorage.getItem("outreachos_session")).organization.name).toBe("Plantiers");
});

test("without a cached identity it still waits for the server, as before", async () => {
  localStorage.setItem("outreachos_token", "t");
  let release;
  api.get.mockReturnValue(new Promise((r) => { release = r; }));
  await mount();
  expect(auth.loading).toBe(true);
  expect(auth.user).toBeNull();
  await act(async () => release({ data: ME }));
  expect(auth.loading).toBe(false);
  expect(auth.user.id).toBe("u1");
});

test("a refused token ends the session; an API that is unreachable or waking does not", async () => {
  localStorage.setItem("outreachos_token", "t");
  localStorage.setItem("outreachos_session", JSON.stringify(CACHED));
  api.get.mockRejectedValue({ response: { status: 503 } });
  await mount();
  expect(auth.user.email).toBe("cached@x.example"); // still signed in
  expect(localStorage.getItem("outreachos_token")).toBe("t");
  await act(async () => root.unmount());

  root = createRoot(container);
  api.get.mockRejectedValue({ response: { status: 401 } });
  await mount();
  expect(auth.user).toBeNull();
  expect(localStorage.getItem("outreachos_token")).toBeNull();
  expect(localStorage.getItem("outreachos_session")).toBeNull();
});

test("a cached identity is never trusted without a token", async () => {
  localStorage.setItem("outreachos_session", JSON.stringify(CACHED));
  await mount();
  expect(auth.user).toBeNull();
  expect(auth.loading).toBe(false);
  expect(api.get).not.toHaveBeenCalled();
});

test("signing out forgets the identity and the cached data of the organisation", async () => {
  const original = window.location;
  delete window.location;
  window.location = { href: "/app/dashboard", pathname: "/app/dashboard" };
  try {
    localStorage.setItem("outreachos_token", "t");
    localStorage.setItem("outreachos_session", JSON.stringify(CACHED));
    swr.write("leads", [{ id: 1 }]);
    api.get.mockResolvedValue({ data: ME });
    await mount();
    await act(async () => auth.logout());
    expect(localStorage.getItem("outreachos_token")).toBeNull();
    expect(localStorage.getItem("outreachos_session")).toBeNull();
    expect(swr.read("leads")).toBeNull();
    expect(window.location.href).toBe("/login");
  } finally {
    window.location = original;
  }
});

test("signing in keeps the identity for the next visit", async () => {
  api.post.mockResolvedValue({ data: { access_token: "tok", ...ME } });
  await mount();
  await act(async () => { await auth.login("o@x.example", "pw"); });
  expect(localStorage.getItem("outreachos_token")).toBe("tok");
  expect(JSON.parse(localStorage.getItem("outreachos_session")).user.email).toBe("o@x.example");
  expect(auth.user.email).toBe("o@x.example");
});
