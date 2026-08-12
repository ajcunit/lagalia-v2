import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { paths } from "../../api/generated/schema";

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
