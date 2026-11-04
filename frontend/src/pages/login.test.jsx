import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { toast } from "sonner";
import Login from "@/pages/Login";

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

const mockLogin = jest.fn();
jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    login: mockLogin,
    user: null,
    loading: false,
  }),
}));

jest.mock("sonner", () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

describe("Login page", () => {
  let container;
  let root;

  beforeEach(() => {
    jest.clearAllMocks();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  const renderLogin = async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Login />
        </MemoryRouter>
      );
    });
  };

  test("renders centered card layout with brand, inputs, and accessible labels", async () => {
    await renderLogin();

    // The card sits in the middle of the free height (the page scrolls when it is short); it is the same frame as Register
    const main = container.querySelector('[data-testid="auth-main"]');
    expect(main).not.toBeNull();
    expect(main.className).toContain("items-center");
    expect(main.className).toContain("justify-center");
    expect(container.querySelector('[data-testid="login-page"]').className).toContain("min-h-[100dvh]");

    // Brand and headings
    const logo = container.querySelector('[data-testid="brand-logo"]');
    expect(logo).not.toBeNull();
    expect(container.textContent).toContain("Qualify. Review.");
    expect(container.textContent).toContain("send.");

    // Form and inputs
    const form = container.querySelector('[data-testid="login-form"]');
    expect(form).not.toBeNull();

    const emailInput = container.querySelector('#email-input');
    const emailLabel = container.querySelector('label[for="email-input"]');
    expect(emailInput).not.toBeNull();
    expect(emailLabel).not.toBeNull();
    expect(emailInput.getAttribute("type")).toBe("email");
    expect(emailInput.getAttribute("autocomplete")).toBe("username");

    const passwordInput = container.querySelector('#password-input');
    const passwordLabel = container.querySelector('label[for="password-input"]');
    expect(passwordInput).not.toBeNull();
    expect(passwordLabel).not.toBeNull();
    expect(passwordInput.getAttribute("type")).toBe("password");
    expect(passwordInput.getAttribute("autocomplete")).toBe("current-password");

    // CTA and register link
    const submitBtn = container.querySelector('[data-testid="login-submit-button"]');
    expect(submitBtn).not.toBeNull();
    expect(submitBtn.textContent).toContain("ENTER COMMAND CENTER");

    const registerLink = container.querySelector('[data-testid="goto-register-link"]');
    expect(registerLink).not.toBeNull();
  });

  test("prints no server status of its own: nothing here can be true or false about the server", async () => {
    await renderLogin();
    const text = container.textContent;
    for (const claim of ["ONLINE", "v2.4", "verified", "operational", "healthy", "uptime"]) expect(text).not.toContain(claim);
    expect(text).toContain("Nothing is sent without a person");
  });

  test("the fields are what a password manager looks for", async () => {
    await renderLogin();
    expect(container.querySelector("#email-input").getAttribute("name")).toBe("username");
    expect(container.querySelector("#password-input").getAttribute("name")).toBe("password");
    expect(container.querySelector("form").querySelectorAll("input")).toHaveLength(2);
  });

  const setInputValue = (input, value) => {
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value"
    ).set;
    nativeInputValueSetter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  };

  test("submits credentials and navigates on success", async () => {
    mockLogin.mockResolvedValueOnce({ token: "jwt-token" });
    await renderLogin();

    const emailInput = container.querySelector('#email-input');
    const passwordInput = container.querySelector('#password-input');
    const form = container.querySelector('[data-testid="login-form"]');

    await act(async () => {
      setInputValue(emailInput, "operator@plantiers.com");
      setInputValue(passwordInput, "secret12345");
    });

    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(mockLogin).toHaveBeenCalledWith("operator@plantiers.com", "secret12345");
    expect(toast.success).toHaveBeenCalledWith("Welcome back, operator.");
    expect(mockNavigate).toHaveBeenCalledWith("/app/dashboard");
  });

  test("displays error message and toast on failed login", async () => {
    mockLogin.mockRejectedValueOnce({
      response: { data: { detail: "Invalid email or password" } },
    });
    await renderLogin();

    const emailInput = container.querySelector('#email-input');
    const passwordInput = container.querySelector('#password-input');
    const form = container.querySelector('[data-testid="login-form"]');

    await act(async () => {
      setInputValue(emailInput, "bad@plantiers.com");
      setInputValue(passwordInput, "wrongpass");
    });

    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(mockLogin).toHaveBeenCalledWith("bad@plantiers.com", "wrongpass");
    expect(toast.error).toHaveBeenCalledWith("Invalid email or password");
    const alert = container.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert.textContent).toContain("Invalid email or password");
  });
});
