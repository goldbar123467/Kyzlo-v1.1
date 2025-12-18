import { GET as health } from "@/app/api/health/route";

describe("health route", () => {
  it("returns ok", async () => {
    const res = health();
    const json = await (res as Response).json();
    expect((res as Response).status).toBe(200);
    expect(json).toMatchObject({ status: "ok" });
  });
});
