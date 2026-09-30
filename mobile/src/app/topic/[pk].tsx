import { Stack, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';

import { PendingBadges, TopicItem } from '@/components/TopicList';
import { Badge, Notice, Row, Status } from '@/components/ui';
import { api, errorText, type Topic } from '@/lib/api';
import { size, themed, useColors } from '@/lib/theme';

export default function TopicScreen() {
  const s = useStyles();
  const c = useColors();
  const { pk } = useLocalSearchParams<{ pk: string }>();
  const [t, setT] = useState<Topic | null>(null);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setT(await api<Topic>(`topics/${pk}/`));
      setError('');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setRefreshing(false);
    }
  }, [pk]);

  useEffect(() => {
    load();
  }, [load]);

  if (!t) return <Status error={error} onRetry={load} />;
  return (
    <ScrollView
      contentContainerStyle={s.page}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => (setRefreshing(true), load())} tintColor={c.accent} />
      }>
      <Stack.Screen options={{ title: t.parent ? t.parent.title : 'Konu' }} />
      {error ? <Notice tone="error">{error}</Notice> : null}
      <Text style={s.h1}>{t.title}</Text>
      <Row>
        {t.locked && <Badge label="Kapalı" />}
        {t.hidden && <Badge label="Gizli" tone="danger" />}
        <PendingBadges pending={t.pending} />
      </Row>
      <Text style={s.meta}>
        {t.author} · {t.created}
      </Text>
      {t.masked ? (
        <Notice>Bu konu moderasyonla gizlendi.</Notice>
      ) : (
        <>
          {t.hidden && <Notice>Bu konu moderasyonla gizlendi; metnini yalnızca sen ve yöneticiler görüyor.</Notice>}
          {t.description ? <Text style={s.text}>{t.description}</Text> : null}
        </>
      )}
      {t.n_subs && (
        <View>
          <Text style={s.h2}>Alt konular</Text>
          {t.subs.length ? (
            t.subs.map((sub) => <TopicItem key={sub.pk} t={sub} showParent={false} />)
          ) : (
            <Text style={s.meta}>Açık alt konu yok.</Text>
          )}
        </View>
      )}
    </ScrollView>
  );
}

const useStyles = themed((c) => ({
  page: { padding: size.s3, gap: size.s2, paddingBottom: size.s4 * 2 },
  h1: { color: c.text, fontSize: size.xl, fontWeight: '800', lineHeight: 34 },
  h2: { color: c.text, fontSize: size.lg, fontWeight: '700', marginTop: size.s4, marginBottom: size.s2 },
  meta: { color: c.muted, fontSize: size.sm },
  text: { color: c.text, fontSize: 16, lineHeight: 25 },
}));
