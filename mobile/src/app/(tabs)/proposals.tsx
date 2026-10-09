import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { Turnout } from '@/components/Bars';
import { Badge, Button, Status } from '@/components/ui';
import { api, errorText, type ProposalItem } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { size, themed, useColors } from '@/lib/theme';

/** Açık öneri satırı (voting/_item.html): tür, başlık, "Oy ver", katılım ya da tartışmanın kalan süresi. */
function Item({ p, quorum }: { p: ProposalItem; quorum: number }) {
  const s = useStyles();
  return (
    <Pressable
      onPress={() => router.push(`/proposal/${p.slug}/${p.pk}`)}
      accessibilityRole="link"
      style={({ pressed }) => [s.item, pressed && s.pressed]}>
      <Badge label={p.kind} />
      <Text style={s.title}>{p.title}</Text>
      {p.voted === false && <Badge label="Oy ver" tone="todo" />}
      {p.discussion ? (
        <Text style={s.small}>Oylamaya {p.left} kaldı</Text>
      ) : (
        <Turnout n={p.participants} quorum={quorum} left={p.left} />
      )}
    </Pressable>
  );
}

function Proposals() {
  const s = useStyles();
  const c = useColors();
  const { me } = useAuth();
  const [data, setData] = useState<{ quorum: number; results: ProposalItem[] } | null>(null);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api('proposals/'));
      setError('');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setRefreshing(false);
    }
  }, []);

  // sekmeye her gelişte: öneriye oy verip dönünce "Oy ver" ve katılım güncel
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const voting = data?.results.filter((p) => !p.discussion) ?? [];
  const talk = data?.results.filter((p) => p.discussion) ?? [];
  return (
    <ScrollView
      contentContainerStyle={s.page}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => {
            setRefreshing(true);
            load();
          }}
          tintColor={c.accent}
        />
      }>
      <Button
        kind="primary"
        title="Bilirkişilik önerisi"
        onPress={() => router.push(me ? '/new/expert' : '/login')}
        style={s.start}
      />
      {!data ? (
        <Status error={error} onRetry={load} />
      ) : (
        <>
          <Text style={s.h2}>Oylamada</Text>
          {voting.map((p) => (
            <Item key={p.slug + p.pk} p={p} quorum={data.quorum} />
          ))}
          {!voting.length && <Text style={s.small}>Süren oylama yok.</Text>}
          {talk.length > 0 && (
            <View>
              <Text style={s.h2}>Tartışmada</Text>
              {talk.map((p) => (
                <Item key={p.slug + p.pk} p={p} quorum={data.quorum} />
              ))}
            </View>
          )}
        </>
      )}
    </ScrollView>
  );
}

export default function ProposalsScreen() {
  const { session } = useAuth();
  return <Proposals key={session} />; // "Oy ver" rozetleri kişiye özel
}

const useStyles = themed((c) => ({
  page: { padding: size.s3, paddingBottom: size.s4 * 2 },
  start: { alignSelf: 'flex-start' },
  h2: {
    color: c.muted,
    fontSize: size.xs,
    fontWeight: '800',
    letterSpacing: 1,
    textTransform: 'uppercase',
    marginTop: size.s4,
    marginBottom: size.s1,
  },
  item: { gap: 4, paddingVertical: 11, borderBottomWidth: 1, borderColor: c.line },
  pressed: { backgroundColor: c.surface },
  title: { color: c.text, fontSize: 16, fontWeight: '600' },
  small: { color: c.muted, fontSize: size.sm },
}));
