import { create } from "zustand";

type HealthStatus = "idle" | "loading" | "ok" | "error";

type HealthState = {
  status: HealthStatus;
  error: string | null;
  fetchHealth: () => Promise<void>;
};

export const useHealthStore = create<HealthState>((set) => ({
  status: "idle",
  error: null,
  fetchHealth: async () => {
    set({ status: "loading", error: null });

    try {
      const response = await fetch("/api/health");

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      set({ status: "ok", error: null });
    } catch (error) {
      set({
        status: "error",
        error: error instanceof Error ? error.message : "Unknown error",
      });
    }
  },
}));
