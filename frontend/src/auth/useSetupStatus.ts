import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

export function useSetupStatus() {
  return useQuery({
    queryKey: ["setup-status"],
    staleTime: 60_000,
    retry: 1,
    queryFn: async () => {
      const { data, error } = await api.GET("/setup/status");
      if (error !== undefined) throw new Error("setup");
      return data;
    },
  });
}
