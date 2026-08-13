import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";

export type Webhook = components["schemas"]["Webhook"];
export type WebhookDelivery = components["schemas"]["WebhookDelivery"];

export function useWebhooks() {
  return useQuery({
    queryKey: ["webhooks"],
    queryFn: async () => {
      const { data, error } = await api.GET("/webhooks");
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function useCreateWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { name: string; url: string; events: string[] }) => {
      const { data, error } = await api.POST("/webhooks", { body });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["webhooks"] }),
  });
}

export function useUpdateWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      body,
    }: {
      id: number;
      body: { name?: string; url?: string; events?: string[]; active?: boolean };
    }) => {
      const { data, error } = await api.PATCH("/webhooks/{id}", {
        params: { path: { id } },
        body,
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["webhooks"] }),
  });
}

export function useDeleteWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const { error } = await api.DELETE("/webhooks/{id}", { params: { path: { id } } });
      if (error !== undefined) throw error;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["webhooks"] }),
  });
}

export function useTestWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const { data, error } = await api.POST("/webhooks/{id}/actions/test", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["webhook-deliveries"] }),
  });
}

export function useWebhookDeliveries(id: number | null) {
  return useQuery({
    queryKey: ["webhook-deliveries", id],
    enabled: id !== null,
    refetchInterval: 5000,
    queryFn: async () => {
      const { data, error } = await api.GET("/webhooks/{id}/deliveries", {
        params: { path: { id: id ?? 0 } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
}
