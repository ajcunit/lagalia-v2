import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components, paths } from "../../api/generated/schema";

export type ContractorRanking = components["schemas"]["ContractorRanking"];
export type ContractorDuplicate = components["schemas"]["ContractorDuplicate"];

export type ContractorsListParams = NonNullable<
  paths["/contractors"]["get"]["parameters"]["query"]
>;

export function useContractors(params: ContractorsListParams) {
  return useQuery({
    queryKey: ["contractors", params],
    queryFn: async () => {
      const { data, error } = await api.GET("/contractors", { params: { query: params } });
      if (error !== undefined) throw error;
      return data;
    },
    placeholderData: (previous) => previous,
  });
}

export function useContractor(id: number) {
  return useQuery({
    queryKey: ["contractor", id],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/contractors/{id}", {
        params: { path: { id } },
      });
      if (error !== undefined)
        throw Object.assign(new Error("contractor"), { status: response.status });
      return data;
    },
    retry: false,
  });
}

export function useContractorDuplicates(status: "pending" | "merged" | "rejected") {
  return useQuery({
    queryKey: ["contractor-duplicates", status],
    queryFn: async () => {
      const { data, error } = await api.GET("/contractors/duplicates", {
        params: { query: { status, "page[size]": 50 } },
      });
      if (error !== undefined) throw error;
      return data;
    },
    placeholderData: (previous) => previous,
  });
}

export type ContractorDuplicateGroup = components["schemas"]["ContractorDuplicateGroup"];

export function useDuplicateGroups(cursor?: string) {
  return useQuery({
    queryKey: ["contractor-duplicate-groups", cursor],
    queryFn: async () => {
      const { data, error } = await api.GET("/contractors/duplicates/groups", {
        params: { query: { "page[size]": 25, "page[cursor]": cursor } },
      });
      if (error !== undefined) throw error;
      return data;
    },
    placeholderData: (previous) => previous,
  });
}

export function useResolveGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      tax_id: string;
      action: "merge" | "reject";
      canonical_id?: number | null;
    }) => {
      const { data, error } = await api.POST("/contractors/duplicates/groups/resolve", {
        body,
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contractor-duplicate-groups"] });
      void queryClient.invalidateQueries({ queryKey: ["contractor-duplicates"] });
      void queryClient.invalidateQueries({ queryKey: ["contractors"] });
    },
  });
}

export function useResolveDuplicate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      action,
      notes,
    }: {
      id: number;
      action: "merge_1" | "merge_2" | "reject";
      notes?: string;
    }) => {
      const { data, error } = await api.POST("/contractors/duplicates/{id}/actions/resolve", {
        params: { path: { id } },
        body: { action, notes },
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contractor-duplicates"] });
      void queryClient.invalidateQueries({ queryKey: ["contractors"] });
    },
  });
}
