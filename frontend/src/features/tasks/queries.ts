import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components, paths } from "../../api/generated/schema";

export type Task = components["schemas"]["Task"];
export type TaskCreate = components["schemas"]["TaskCreate"];
export type TaskSuggestion = components["schemas"]["TaskSuggestion"];

export type TasksListParams = NonNullable<paths["/tasks"]["get"]["parameters"]["query"]>;

function useInvalidateTasks() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["tasks"] });
    void queryClient.invalidateQueries({ queryKey: ["tasks-calendar"] });
    void queryClient.invalidateQueries({ queryKey: ["task-suggestions"] });
  };
}

export function useTasks(params: TasksListParams) {
  return useQuery({
    queryKey: ["tasks", params],
    queryFn: async () => {
      const { data, error } = await api.GET("/tasks", { params: { query: params } });
      if (error !== undefined) throw error;
      return data;
    },
    placeholderData: (previous) => previous,
  });
}

export function useTasksCalendar(from: string, to: string) {
  return useQuery({
    queryKey: ["tasks-calendar", from, to],
    queryFn: async () => {
      const { data, error } = await api.GET("/tasks/calendar", {
        params: { query: { from, to } },
      });
      if (error !== undefined) throw error;
      return data;
    },
    placeholderData: (previous) => previous,
  });
}

export function useTaskSuggestions(enabled: boolean) {
  return useQuery({
    queryKey: ["task-suggestions"],
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET("/tasks/suggestions");
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function useCreateTask() {
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: async (body: TaskCreate) => {
      const { data, error } = await api.POST("/tasks", { body });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: invalidate,
  });
}

export function useTaskAction() {
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: async ({
      id,
      action,
      notes,
    }: {
      id: number;
      action: "start" | "complete" | "cancel" | "reopen";
      notes?: string;
    }) => {
      const path = `/tasks/{id}/actions/${action}` as "/tasks/{id}/actions/complete";
      const { data, error } = await api.POST(path, {
        params: { path: { id } },
        body: notes ? { resolution_notes: notes } : undefined,
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: invalidate,
  });
}
