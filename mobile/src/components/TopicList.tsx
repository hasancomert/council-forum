// Konu listesi (ana sayfa ve bir konunun alt konuları): sekmeler, sıralama, konu satırları (topics/_row.html).
import { router } from 'expo-router';
import { useState, type ReactElement } from 'react';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';

import type { Pending, TopicList as List, TopicRow } from '@/lib/api';
import { usePaged } from '@/lib/paged';
import { size, themed, useColors } from '@/lib/theme';

import { Badge, Button, Row, Status } from './ui';

/** Süren kapatma/silme oylaması rozetleri. */
export function PendingBadges({ pending }: { pending: Pending[] }) {
  return pending.map((p) => <Badge key={p.pk + p.slug} label={p.label} tone="pending" />);
}

export function TopicItem({ t, showParent = true }: { t: TopicRow; showParent?: boolean }) {
  const s = useStyles();
  return (
    <Pressable
      onPress={() => router.push(`/topic/${t.pk}`)}
      accessibilityRole="link"
      style={({ pressed }) => [s.row, pressed && s.pressed]}>
      <Text style={s.score} accessibilityLabel={`puan ${t.score}`}>
        {t.score}
      </Text>
      <View style={s.body}>
        <Text style={s.title}>
          {showParent && t.parent && <Text style={s.parent}>{t.parent.title} › </Text>}
          {t.title}
        </Text>
        {(t.locked || t.pending.length > 0) && (
          <Row>
            {t.locked && <Badge label="Kapalı" />}
            <PendingBadges pending={t.pending} />
          </Row>
        )}
        <Text style={s.meta}>
          {t.comments} yorum{t.subs ? ` · ${t.subs} alt konu` : ''} · {t.created}
        </Text>
      </View>
    </Pressable>
  );
}

/** parent verilirse yalnızca o konunun alt konuları (sitedeki ?parent=). */
export function TopicList({ parent, header }: { parent?: string; header?: ReactElement }) {
  const s = useStyles();
  const c = useColors();
  const [tab, setTab] = useState(parent ? 'sub' : 'main');
  const [sort, setSort] = useState('');
  const query = Object.entries({ tab, sort, parent })
    .filter(([, v]) => v)
    .map(([k, v]) => `${k}=${v}`)
    .join('&');
  const list = usePaged<TopicRow, List>(`topics/?${query}`);
  const meta = list.meta;

  return (
    <FlatList
      data={list.items}
      keyExtractor={(t) => String(t.pk)}
      renderItem={({ item }) => <TopicItem t={item} showParent={!parent} />}
      onEndReached={list.more}
      onEndReachedThreshold={0.5}
      refreshControl={<RefreshControl refreshing={list.refreshing} onRefresh={list.refresh} tintColor={c.accent} />}
      contentContainerStyle={s.content}
      ListHeaderComponent={
        <View>
          {header}
          {meta && (
            <>
              <View style={s.tabs} accessibilityRole="tablist">
                {meta.tabs.map(([key, label]) => (
                  <Pressable
                    key={key}
                    onPress={() => {
                      setTab(key);
                      setSort(''); // her sekmenin kendi varsayılanı (Kapalı: en yeni)
                    }}
                    accessibilityRole="tab"
                    accessibilityState={{ selected: key === tab }}
                    style={[s.tab, key === tab && s.tabOn]}>
                    <Text style={[s.tabText, key === tab && s.tabTextOn]}>{label}</Text>
                  </Pressable>
                ))}
              </View>
              <Row style={s.sorts}>
                <Text style={s.meta}>Sırala:</Text>
                {meta.sorts.map(([key, label]) => (
                  <Button key={key} kind="chip" title={label} pressed={key === (sort || meta.sort)} onPress={() => setSort(key)} />
                ))}
              </Row>
            </>
          )}
        </View>
      }
      ListEmptyComponent={
        list.busy || list.error ? (
          <Status error={list.error} onRetry={list.reload} />
        ) : (
          <Text style={s.empty}>Bu sekmede konu yok.</Text>
        )
      }
      ListFooterComponent={list.items.length > 0 && list.busy ? <Status /> : null}
    />
  );
}

const useStyles = themed((c) => ({
  content: { padding: size.s3, paddingBottom: size.s4 * 2 },
  tabs: { flexDirection: 'row', borderBottomWidth: 1, borderColor: c.line, marginBottom: size.s3 },
  tab: { minHeight: 44, justifyContent: 'center', paddingHorizontal: size.s3, borderBottomWidth: 3, borderColor: 'transparent' },
  tabOn: { borderColor: c.accent },
  tabText: { color: c.muted, fontSize: 15, fontWeight: '600' },
  tabTextOn: { color: c.text, fontWeight: '700' },
  sorts: { marginBottom: size.s2 },
  row: {
    flexDirection: 'row',
    gap: size.s3,
    paddingVertical: 12,
    paddingHorizontal: size.s2,
    borderBottomWidth: 1,
    borderColor: c.line,
  },
  pressed: { backgroundColor: c.surface },
  score: {
    alignSelf: 'flex-start',
    width: 48,
    minHeight: size.chip,
    paddingTop: 7,
    borderRadius: size.radius,
    overflow: 'hidden',
    backgroundColor: c.accentSoft,
    color: c.accent,
    fontWeight: '800',
    fontSize: 16,
    textAlign: 'center',
    fontVariant: ['tabular-nums'],
  },
  body: { flex: 1, gap: size.s1 },
  title: { color: c.text, fontSize: 17, fontWeight: '700' },
  parent: { color: c.accent, fontWeight: '600' },
  meta: { color: c.muted, fontSize: size.sm },
  empty: {
    padding: size.s4,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: c.line,
    borderRadius: size.radiusLg,
    color: c.muted,
    textAlign: 'center',
  },
}));
