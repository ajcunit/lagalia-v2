import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { api } from "../api/client";
import { asProblem } from "../api/problem";
import type { components } from "../api/generated/schema";
import { clearSession, onSessionExpired, restoreSession, setSession } from "./session";

type User = components["schemas"]["User"];

export type AuthStatus = "loading" | "anonymous" | "authenticated";

export interface Permissions {
  role: components["schemas"]["Role"];
  actions: string[];
  can_switch_view?: boolean;
}

interface AuthContextValue {
  status: AuthStatus;
  user: User | undefined;
  permissions: Permissions | undefined;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const queryClient = useQueryClient();

  useEffect(() => {
    onSessionExpired(() => setStatus("anonymous"));
    void restoreSession().then((restored) =>
      setStatus(restored ? "authenticated" : "anonymous"),
    );
  }, []);

  // Una crida per sessió (staleTime infinit): la UI no dedueix res del rol.
  const me = useQuery({
    queryKey: ["me"],
    enabled: status === "authenticated",
    staleTime: Infinity,
    queryFn: async () => {
      const { data, error } = await api.GET("/me");
      if (error !== undefined) throw new Error("me");
      return data;
    },
  });

  const permissions = useQuery({
    queryKey: ["me-permissions"],
    enabled: status === "authenticated",
    staleTime: Infinity,
    queryFn: async () => {
      const { data, error } = await api.GET("/me/permissions");
      if (error !== undefined) throw new Error("permissions");
      return data;
    },
  });

  const login = useCallback(
    async (email: string, password: string) => {
      const { data, error, response } = await api.POST("/auth/login", {
        body: { email, password },
      });
      if (error !== undefined || data === undefined) {
        throw asProblem(error, response);
      }
      setSession(data);
      queryClient.removeQueries();
      setStatus("authenticated");
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    await api.POST("/auth/logout").catch(() => undefined);
    clearSession();
    queryClient.removeQueries();
    setStatus("anonymous");
  }, [queryClient]);

  return (
    <AuthContext.Provider
      value={{ status, user: me.data, permissions: permissions.data, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) throw new Error("useAuth fora d'AuthProvider");
  return value;
}
