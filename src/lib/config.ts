import path from "node:path";

export type StateMode = "local" | "mock" | "remote";

export type StateConfig = {
  mode: StateMode;
  localStatePath: string;
  fixturePath: string;
  remoteUrl: string;
};

export function getStateConfig(modeOverride?: StateMode): StateConfig {
  const mode = (modeOverride ??
    (process.env.NEXT_PUBLIC_STATE_MODE as StateMode | undefined) ??
    "remote") as StateMode;

  const localStatePath =
    process.env.LOCAL_STATE_PATH ??
    path.resolve(process.cwd(), "../reports/state.json");

  const fixturePath =
    process.env.STATE_FIXTURE_PATH ??
    path.resolve(process.cwd(), "fixtures/state.sample.json");

  const remoteUrl =
    process.env.STATE_REMOTE_URL ?? process.env.NEXT_PUBLIC_STATE_URL ?? "";

  return {
    mode,
    localStatePath,
    fixturePath,
    remoteUrl,
  };
}
