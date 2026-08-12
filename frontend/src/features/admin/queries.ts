import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components, paths } from "../../api/generated/schema";

export type User = components["schemas"]["User"];
export type Department = components["schemas"]["Department"];
export type UserCreate = components["schemas"]["UserCreate"];
export type UserUpdate = components["schemas"]["UserUpdate"];
export type DepartmentCreate = components["schemas"]["DepartmentCreate"];
export type DepartmentUpdate = components["schemas"]["DepartmentUpdate"];

type UsersListParams = NonNullable<paths["/users"]["get"]["parameters"]["query"]>;

export function useUsers(params: UsersListParams) {
  return useQuery({
    queryKey: ["admin-users", params],
    queryFn: async () => {
      const { data, error } = await api.GET("/users", { params: { query: params } });
      if (error !== undefined) throw error;
      return data;
    },
    placeholderData: (previous) => previous,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: UserCreate) => {
      const { data, error } = await api.POST("/users", { body });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: UserUpdate }) => {
      const { data, error } = await api.PATCH("/users/{id}", {
        params: { path: { id } },
        body,
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}

export function useDepartments(includeInactive = true) {
  return useQuery({
    queryKey: ["admin-departments", includeInactive],
    queryFn: async () => {
      const { data, error } = await api.GET("/departments", {
        params: { query: { "page[size]": 500 } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function useCreateDepartment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: DepartmentCreate) => {
      const { data, error } = await api.POST("/departments", { body });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-departments"] });
      void queryClient.invalidateQueries({ queryKey: ["department-options"] });
    },
  });
}

export function useUpdateDepartment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: DepartmentUpdate }) => {
      const { data, error } = await api.PATCH("/departments/{id}", {
        params: { path: { id } },
        body,
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-departments"] });
      void queryClient.invalidateQueries({ queryKey: ["department-options"] });
    },
  });
}

export function problemMessage(error: unknown): string {
  if (error && typeof error === "object") {
    const problem = error as { title?: string; detail?: string };
    return problem.detail ?? problem.title ?? String(error);
  }
  return String(error);
}
