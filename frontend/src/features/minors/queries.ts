import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components, paths } from "../../api/generated/schema";

export type MinorContract = components["schemas"]["MinorContract"];
export type MinorContractUpdate = components["schemas"]["MinorContractUpdate"];

export type MinorsListParams = NonNullable<
  paths["/minor-contracts"]["get"]["parameters"]["query"]
>;

export function useMinorContracts(params: MinorsListParams) {
  return useQuery({
    queryKey: ["minor-contracts", params],
    queryFn: async () => {
      const { data, error } = await api.GET("/minor-contracts", {
        params: { query: params },
      });
      if (error !== undefined) throw error;
      return data;
    },
    placeholderData: (previous) => previous,
  });
}

export function useMinorContract(id: number) {
  return useQuery({
    queryKey: ["minor-contract", id],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/minor-contracts/{id}", {
        params: { path: { id } },
      });
      if (error !== undefined)
        throw Object.assign(new Error("minor-contract"), { status: response.status });
      return data;
    },
    retry: false,
  });
}

export function useUpdateMinorContract(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: MinorContractUpdate) => {
      const { data, error } = await api.PATCH("/minor-contracts/{id}", {
        params: { path: { id } },
        body,
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["minor-contract", id] });
      void queryClient.invalidateQueries({ queryKey: ["minor-contracts"] });
    },
  });
}
