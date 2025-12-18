import { validateState } from "@/lib/stateSchema";
import fixture from "../fixtures/state.sample.json";

describe("state schema", () => {
  it("validates the fixture", () => {
    expect(() => validateState(fixture)).not.toThrow();
  });
});
