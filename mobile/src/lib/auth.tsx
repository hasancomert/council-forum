import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

import { api, hasToken, loadToken, onSessionEnd, setToken, type Me } from './api';

type Auth = {
  me: Me | null; // giriş yoksa (ya da henüz gelmediyse) null
  session: number; // giriş/çıkışta artar: kişiye özel ekranlar key={session} ile baştan yüklenir
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>; // rol, oy hakkı, açık öneri sayısı değişmiş olabilir
};

const AuthContext = createContext<Auth | null>(null);

/** Kayıtlı jeton okunana kadar ekran çizilmez: ilk istekler jetonla gitsin. me arkadan gelir (sunucu yavaşsa
 *  uygulama beklemez). */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState(0);
  const changed = () => setSession((n) => n + 1);

  // sabit fonksiyon: ekranlar odak efektinde çağırır (her çizimde yenisi olsa efekt döngüye girerdi)
  const refresh = useCallback(async () => {
    if (hasToken()) setMe(await api<Me>('me/').catch(() => null)); // 401'de api() jetonu siler
  }, []);

  useEffect(() => {
    onSessionEnd(() => {
      setMe(null);
      changed();
    });
    loadToken()
      .catch(() => {})
      .finally(() => {
        setReady(true);
        refresh();
      });
  }, [refresh]);

  const auth: Auth = {
    me,
    session,
    refresh,
    login: async (username, password) => {
      const d = await api<{ token: string; me: Me }>('login/', { username, password });
      await setToken(d.token);
      setMe(d.me);
      changed();
    },
    logout: async () => {
      await setToken(null); // jeton yalnızca telefonda; sunucuda tutulmaz
      setMe(null);
      changed();
    },
  };
  return <AuthContext value={auth}>{ready ? children : null}</AuthContext>;
}

export function useAuth() {
  return useContext(AuthContext)!;
}
