import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";

export function useFolders() {
  return useQuery({
    queryKey: ["folders"],
    queryFn: async () => {
      const { data, error } = await api.GET("/folders");
      if (error !== undefined) throw error;
      return data;
    },
  });
}
