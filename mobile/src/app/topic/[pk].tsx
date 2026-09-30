import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { CommentThread } from '@/components/Comments';
import { PendingBadges, TopicItem } from '@/components/TopicList';
import { ReportBox, VoteButtons } from '@/components/Vote';
import { Badge, Button, Notice, Row, Status } from '@/components/ui';
import { api, errorText, openSite, type Topic } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { size, themed } from '@/lib/theme';

// Sık kullanılanlar önde; konunun kendisini değiştiren öneriler "Diğer öneriler"de (topics/detail.html).
const MORE = ['edit', 'close', 'delete'];

function Actions({ t }: { t: Topic }) {
  const s = useStyles();
  const [more, setMore] = useState(false);
  const link = ([slug, label]: [string, string]) => (
    <Button key={slug} kind="chip" title={label} onPress={() => router.push(`/new/${slug}?topic=${t.pk}`)} />
  );
  const others = t.actions.filter(([slug]) => MORE.includes(slug));
  return (
    <View style={s.actions}>
      <Row>
        {t.actions.filter(([slug]) => !MORE.includes(slug)).map(link)}
        {others.length > 0 && (
          <Button kind="chip" title={`Diğer öneriler ${more ? '▴' : '▾'}`} pressed={more} onPress={() => setMore(!more)} />
        )}
      </Row>
      {more && <Row>{others.map(link)}</Row>}
    </View>
  );
}

function TopicHeader({ t }: { t: Topic }) {
  const s = useStyles();
  const { me } = useAuth();
  const [reporting, setReporting] = useState(false);
  const n = t.n_subs;
  return (
    <View style={s.head}>
      {t.parent && (
        <Button kind="small" title={`← ${t.parent.title}`} onPress={() => router.push(`/topic/${t.parent!.pk}`)} style={s.back} />
      )}
      <Text style={s.h1}>{t.title}</Text>
      <Row>
        {t.locked && <Badge label="Kapalı" />}
        {t.hidden && <Badge label="Gizli" tone="danger" />}
        <PendingBadges pending={t.pending} />
      </Row>
      <Row>
        <VoteButtons path={`topics/${t.pk}/vote/`} score={t.score} mine={t.mine} why={t.why} />
        <Text style={s.meta}>
          {t.author} · {t.created}
        </Text>
        {me?.moderator ? (
          <Button kind="small" title="Moderasyon" onPress={() => openSite(`/mod/${t.ct}/${t.pk}/`)} />
        ) : (
          t.can_report && (
            <Button kind="quiet" title="⚑" label="Şikayet et" pressed={reporting} onPress={() => setReporting(!reporting)} />
          )
        )}
      </Row>
      {reporting && <ReportBox ct={t.ct} pk={t.pk} />}
      {t.masked ? (
        <Notice>Bu konu moderasyonla gizlendi.</Notice>
      ) : (
        <>
          {t.hidden && <Notice>Bu konu moderasyonla gizlendi; metnini yalnızca sen ve yöneticiler görüyor.</Notice>}
          {t.description ? (
            <Text style={s.text} selectable>
              {t.description}
            </Text>
          ) : null}
        </>
      )}
      {t.actions.length > 0 && <Actions t={t} />}
      {n && (
        <View>
          <Text style={s.h2}>Alt konular</Text>
          {t.subs.map((sub) => (
            <TopicItem key={sub.pk} t={sub} showParent={false} />
          ))}
          {!t.subs.length && <Text style={s.meta}>Açık alt konu yok.</Text>}
          <Row style={s.more}>
            {n.open > t.subs.length && (
              <Button kind="chip" title={`Tüm alt konular (${n.open}) →`} onPress={() => router.push(`/subtopics/${t.pk}`)} />
            )}
            {n.closed > 0 && (
              <Button
                kind="chip"
                title={`Kapalı alt konular (${n.closed}) →`}
                onPress={() => router.push(`/subtopics/${t.pk}?tab=closed`)}
              />
            )}
          </Row>
        </View>
      )}
    </View>
  );
}

function TopicView({ pk }: { pk: string }) {
  const [t, setT] = useState<Topic | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setT(await api<Topic>(`topics/${pk}/`));
      setError('');
    } catch (e) {
      setError(errorText(e));
    }
  }, [pk]);

  useEffect(() => {
    load();
  }, [load]);

  if (!t) return <Status error={error} onRetry={load} />;
  return (
    <>
      <Stack.Screen options={{ title: t.parent ? 'Alt konu' : 'Konu' }} />
      <CommentThread
        target={{ ct: t.ct, pk: t.pk }}
        onRefresh={load}
        header={
          <>
            {error ? <Notice tone="error">{error}</Notice> : null}
            <TopicHeader t={t} />
          </>
        }
      />
    </>
  );
}

export default function TopicScreen() {
  const { pk } = useLocalSearchParams<{ pk: string }>();
  const { session } = useAuth();
  return <TopicView key={session} pk={pk} />; // giriş/çıkışta baştan: oylarım, yazabilir miyim, bağlantılar
}

const useStyles = themed((c) => ({
  head: { gap: size.s2 },
  back: { alignSelf: 'flex-start', marginLeft: -10 },
  h1: { color: c.text, fontSize: size.xl, fontWeight: '800', lineHeight: 34 },
  h2: { color: c.text, fontSize: size.lg, fontWeight: '700', marginTop: size.s4, marginBottom: size.s1 },
  meta: { color: c.muted, fontSize: size.sm },
  text: { color: c.text, fontSize: 16, lineHeight: 25 },
  more: { marginTop: size.s3 },
  actions: { gap: size.s2, marginTop: size.s2 },
}));
