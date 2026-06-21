import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  clearToken,
  fetchCurrentUser,
  getToken,
  login as apiLogin,
  register as apiRegister,
  type UserProfile,
} from "@/lib/api";
import { AuthContext } from "@/providers/auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(() => Boolean(getToken()));

  useEffect(() => {
    const token = getToken();
    if (!token) {
      return;
    }

    fetchCurrentUser()
      .then(setUser)
      .catch(() => {
        clearToken();
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await apiLogin(email, password);
    const profile = await fetchCurrentUser();
    setUser(profile);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    await apiRegister(email, password);
    await apiLogin(email, password);
    const profile = await fetchCurrentUser();
    setUser(profile);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, login, register, logout }),
    [user, isLoading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
