import { useCallback, useEffect, useRef, useState } from 'react';

import { api, errorText, type Paged } from './api';

/** Sayfalı liste (konular, yorumlar): ilk sayfa, aşağı çekip yenileme ve kaydırdıkça sonraki sayfa.
 *  path değişince (sekme, sıralama) baştan yüklenir; yalnızca son isteğin yanıtı yazılır (eskisi geç gelse de). */
export function usePaged<T extends { pk: number }, M extends Paged<T> = Paged<T>>(path: string) {
  const [meta, setMeta] = useState<M | null>(null);
  const [items, setItems] = useState<T[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const last = useRef(0);

  const load = useCallback(
    async (page: number) => {
      const n = ++last.current;
      setBusy(true);
      try {
        const d = await api<M>(`${path}${path.includes('?') ? '&' : '?'}page=${page}`);
        if (n !== last.current) return;
        setMeta(d);
        // "En popüler" sıralaması sayfalar arasında değişebilir: aynı konu iki kez listelenmesin
        setItems((old) => (page === 1 ? d.results : [...old, ...d.results.filter((r) => !old.some((o) => o.pk === r.pk))]));
        setError('');
      } catch (e) {
        if (n === last.current) setError(errorText(e));
      } finally {
        if (n === last.current) {
          setBusy(false);
          setRefreshing(false);
        }
      }
    },
    [path],
  );

  useEffect(() => {
    setItems([]); // başka sekme/sıralama: eski satırlar yeni yanıt gelene kadar kalmasın
    load(1);
  }, [load]);

  return {
    meta,
    items,
    error,
    busy,
    refreshing,
    reload: () => load(1),
    refresh: () => {
      setRefreshing(true);
      load(1);
    },
    more: () => {
      if (!busy && meta && meta.page < meta.pages) load(meta.page + 1);
    },
  };
}
