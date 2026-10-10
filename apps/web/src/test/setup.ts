import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// How long findBy and waitFor wait for a screen to settle. A busy machine renders the larger
// screens in more than the default second; a test still fails when the element never comes.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
