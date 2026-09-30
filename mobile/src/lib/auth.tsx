import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

import { api, hasToken, loadToken, onSessionEnd, setToken, type Me } from './api';

type Auth = {
  me: Me | null; // giriş yoksa null
  ready: boolean; // kayıtlı jeton okundu mu
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>; // rol, oy hakkı, açık öneri sayısı değişmiş olabilir
};

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = async () => {
    if (hasToken()) setMe(await api<Me>('me/').catch(() => null)); // 401'de api() jetonu siler
  };

  useEffect(() => {
    onSessionEnd(() => setMe(null));
    loadToken()
      .then(refresh)
      .finally(() => setReady(true));
  }, []);

  const auth: Auth = {
    me,
    ready,
    refresh,
    login: async (username, password) => {
      const d = await api<{ token: string; me: Me }>('login/', { username, password });
      await setToken(d.token);
      setMe(d.me);
    },
    logout: async () => {
      await setToken(null); // jeton yalnızca telefonda; sunucuda tutulmaz
      setMe(null);
    },
  };
  return <AuthContext value={auth}>{children}</AuthContext>;
}

export function useAuth() {
  return useContext(AuthContext)!;
}
