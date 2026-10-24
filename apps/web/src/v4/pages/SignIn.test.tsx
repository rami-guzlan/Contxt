// Sign in: a pasted sign-in link or key is posted to /auth/login, and the key is never shown.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { mockApi } from "../../test/render";
import { keyFrom, SignInPage } from "./SignIn";

describe("Sign in", () => {
  it("posts the key out of a pasted sign-in link, then opens Home", async () => {
    const calls = mockApi({ "POST /auth/login": { status: 204 } });
    const go = vi.fn();
    render(<SignInPage go={go} />);
    const field = screen.getByLabelText("Sign-in link or key");
    expect(field).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();
    await userEvent.type(field, "http://127.0.0.1:8000/auth/login?token=k3y-abc");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await vi.waitFor(() => expect(go).toHaveBeenCalledWith("/"));
    expect(calls[0]).toMatchObject({ method: "POST", path: "/auth/login", body: { token: "k3y-abc" } });
    expect(screen.queryByText(/k3y-abc/)).not.toBeInTheDocument();
  });

  it("takes a pasted key as it is, on Enter", async () => {
    const calls = mockApi({ "POST /auth/login": { status: 204 } });
    const go = vi.fn();
    render(<SignInPage go={go} />);
    await userEvent.type(screen.getByLabelText("Sign-in link or key"), "  plain key  {Enter}");
    await vi.waitFor(() => expect(go).toHaveBeenCalledWith("/"));
    expect(calls[0]?.body).toEqual({ token: "plain key" });
  });

  it("says what to do when the key is wrong", async () => {
    mockApi({ "POST /auth/login": { status: 401, body: { error: { code: "unauthenticated", message: "no" } } } });
    const go = vi.fn();
    render(<SignInPage go={go} />);
    await userEvent.type(screen.getByLabelText("Sign-in link or key"), "old{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("That key didn't work");
    expect(go).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("reads keys from links and leaves other text alone", () => {
    expect(keyFrom("/auth/login?token=a%2Bb")).toBe("a+b");
    expect(keyFrom(" abc ")).toBe("abc");
    expect(keyFrom("")).toBe("");
  });
});
