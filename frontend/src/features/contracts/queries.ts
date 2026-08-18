import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { paths } from "../../api/generated/schema";

function useInvalidateContract(id: number) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["contract", id] });
    void queryClient.invalidateQueries({ queryKey: ["contract-history", id] });
    void queryClient.invalidateQueries({ queryKey: ["contracts"] });
  };
}

export function useFinishContract(id: number) {
  const invalidate = useInvalidateContract(id);
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/contracts/{id}/actions/finish", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: invalidate,
  });
}

export function useDismissExpiry(id: number) {
  const invalidate = useInvalidateContract(id);
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/contracts/{id}/actions/dismiss-expiry", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: invalidate,
  });
}

export function useEnrichContract(id: number) {
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/contracts/{id}/actions/enrich", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function useJobStatus(jobId: string | null) {
  return useQuery({
    queryKey: ["job", jobId],
    enabled: jobId !== null,
    queryFn: async () => {
      const { data, error } = await api.GET("/jobs/{id}", {
        params: { path: { id: jobId ?? "" } },
      });
      if (error !== undefined) throw error;
      return data;
    },
    // Sondeig fins a estat terminal (B-012; la versió SSE arribarà després).
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });
}

type ExportBody = NonNullable<
  paths["/contracts/exports"]["post"]["requestBody"]
>["content"]["application/json"];

export function useCreateExport() {
  return useMutation({
    mutationFn: async (body: ExportBody) => {
      const { data, error } = await api.POST("/contracts/exports", { body });
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export async function downloadExport(jobId: string): Promise<void> {
  const { data, error } = await api.POST("/auth/ephemeral", {
    body: { purpose: "download", resource: jobId },
  });
  if (error !== undefined) throw error;
  const url = `/api/v1/contracts/exports/${jobId}/download?token=${encodeURIComponent(data.token)}`;
  window.location.assign(url);
}

export function useBulkAssignDepartments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      contract_ids: number[];
      department_ids: number[];
      mode: "add" | "replace";
    }) => {
      const { data, error } = await api.POST("/contracts/bulk/assign-departments", { body });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contracts"] });
    },
  });
}

export type ContractsListParams = NonNullable<
  paths["/contracts"]["get"]["parameters"]["query"]
>;

export function useContracts(params: ContractsListParams) {
  return useQuery({
    queryKey: ["contracts", params],
    queryFn: async () => {
      const { data, error } = await api.GET("/contracts", { params: { query: params } });
      if (error !== undefined) throw error;
      return data;
    },
    placeholderData: (previous) => previous,
  });
}

export function useContract(id: number) {
  return useQuery({
    queryKey: ["contract", id],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/contracts/{id}", {
        params: { path: { id } },
      });
      if (error !== undefined) throw Object.assign(new Error("contract"), {
        status: response.status,
      });
      return data;
    },
    retry: false,
  });
}

export function useContractExecutions(id: number) {
  return useQuery({
    queryKey: ["contract-executions", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/contracts/{id}/executions", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function useContractExtensions(id: number) {
  return useQuery({
    queryKey: ["contract-extensions", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/contracts/{id}/extensions", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function useContractModifications(id: number) {
  return useQuery({
    queryKey: ["contract-modifications", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/contracts/{id}/modifications", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function useContractCriteria(id: number) {
  return useQuery({
    queryKey: ["contract-criteria", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/contracts/{id}/criteria", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function useContractCommittee(id: number) {
  return useQuery({
    queryKey: ["contract-committee", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/contracts/{id}/committee", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function useContractDocuments(id: number) {
  return useQuery({
    queryKey: ["contract-documents", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/contracts/{id}/documents", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function useContractHistory(id: number) {
  return useQuery({
    queryKey: ["contract-history", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/contracts/{id}/history", {
        params: { path: { id }, query: { "page[size]": 50 } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function useContractsStats(params: { view?: "user" | "all"; year?: number }) {
  return useQuery({
    queryKey: ["contracts-stats", params],
    queryFn: async () => {
      const { data, error } = await api.GET("/contracts/stats", {
        params: {
          query: {
            view: params.view,
            "filter[year]": params.year,
          },
        },
      });
      if (error !== undefined) throw error;
      return data;
    },
    placeholderData: (previous) => previous,
  });
}

export function useContractsFacets(view: "user" | "all" = "user") {
  return useQuery({
    queryKey: ["contracts-facets", view],
    staleTime: 5 * 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET("/contracts/facets", {
        params: { query: { view } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function useDepartmentOptions() {
  return useQuery({
    queryKey: ["department-options"],
    staleTime: 5 * 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET("/departments", {
        params: { query: { "page[size]": 500 } },
      });
      if (error !== undefined) throw error;
      return data.data;
    },
  });
}
