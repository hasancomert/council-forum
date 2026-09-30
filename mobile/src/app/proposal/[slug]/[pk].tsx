import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { ResultBar, Turnout } from '@/components/Bars';
import { CommentThread } from '@/components/Comments';
import { ReportBox } from '@/components/Vote';
import { Badge, Button, Notice, Row, Status } from '@/components/ui';
import { api, errorText, openSite, type Proposal } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { size, themed } from '@/lib/theme';

/** Oylama bölümü (voting/detail.html): sürerken yalnızca katılım ve benim oyum; bitince sonuç (kural 6). */
function Voting({ p, reload }: { p: Proposal; reload: () => void }) {
  const s = useStyles();
  const { me } = useAuth();
  const [error, setError] = useState('');
  const r = p.result;

  const vote = async (choice: 'yes' | 'no') => {
    try {
      await api(`proposals/${p.slug}/${p.pk}/vote/`, { choice });
      setError('');
      reload();
    } catch (e) {
      setError(errorText(e));
    }
  };

  if (p.status === 'cancelled')
    return (
      <Text style={s.text}>
        Sonuç: <Text style={s.strong}>İptal edildi</Text>. Oylama sonuçlanmadığı için ara sonuç açıklanmaz.
      </Text>
    );
  if (r)
    return (
      <View>
        <Text style={s.text}>
          Sonuç: <Text style={s.strong}>{p.status_label}</Text>
          {r.applied ? ` · ${r.applied}` : ''}
        </Text>
        {r.count > 0 && <ResultBar yes={r.yes} no={r.no} />}
        <Text style={s.text}>
          Evet {r.yes} · Hayır {r.no}
          {r.weighted ? ' (ağırlıklı)' : ''} · katılım {r.count}, yeter sayı {r.quorum}
        </Text>
        {p.status === 'failed' && (
          <Notice>
            Kabul edildi, ama hedefin durumu artık uygun olmadığı için (ör. konu kapandı ya da silindi) uygulanamadı. Aynı
            öneri yeniden açılabilir.
          </Notice>
        )}
      </View>
    );
  return (
    <View style={s.voting}>
      {p.discussion_ends && <Text style={s.text}>Tartışma sürüyor; oylama {p.discussion_ends} tarihinde başlar.</Text>}
      <Text style={s.text}>
        Bitiş: {p.ends} ({p.left} kaldı). Sonuç oylama bitince açıklanır.
      </Text>
      {p.turnout && <Turnout n={p.turnout.n} quorum={p.turnout.quorum} />}
      {!me ? (
        <Button kind="chip" title="Oy vermek için giriş yap" onPress={() => router.push('/login')} style={s.start} />
      ) : (
        <>
          {p.mine && (
            <Text style={s.text}>
              Oyun: <Text style={s.strong}>{p.mine === 'yes' ? 'Evet' : 'Hayır'}</Text> (oylama bitene kadar değiştirebilirsin)
            </Text>
          )}
          {p.accepts &&
            (p.why ? (
              <Text style={s.muted}>{p.why}</Text>
            ) : (
              // iki düğme aynı görünümde: oylama bir seçeneğe yönlendirmesin
              <Row>
                <Button title="Evet" pressed={p.mine === 'yes'} onPress={() => vote('yes')} />
                <Button title="Hayır" pressed={p.mine === 'no'} onPress={() => vote('no')} />
              </Row>
            ))}
          {error ? <Notice tone="error">{error}</Notice> : null}
        </>
      )}
    </View>
  );
}

function ProposalHeader({ p, reload }: { p: Proposal; reload: () => void }) {
  const s = useStyles();
  const { me } = useAuth();
  const [reporting, setReporting] = useState(false);
  return (
    <View style={s.head}>
      <Text style={s.h1}>{p.title}</Text>
      <Row>
        <Badge label={p.kind} />
        {p.status === 'cancelled' && <Badge label="İptal" tone="danger" />}
        {p.hidden && <Badge label="Gizli" tone="danger" />}
      </Row>
      <Row>
        <Text style={s.muted}>
          {p.proposer} · {p.created}
        </Text>
        {me?.moderator ? (
          <Button kind="small" title="Moderasyon" onPress={() => openSite(`/mod/${p.ct}/${p.pk}/`)} />
        ) : (
          p.can_report && (
            <Button kind="quiet" title="⚑" label="Şikayet et" pressed={reporting} onPress={() => setReporting(!reporting)} />
          )
        )}
      </Row>
      {reporting && <ReportBox ct={p.ct} pk={p.pk} />}
      {p.masked ? (
        <Notice>Bu öneri moderasyonla gizlendi.</Notice>
      ) : (
        <>
          {p.hidden && <Notice>Bu öneri moderasyonla gizlendi; metnini yalnızca sen ve yöneticiler görüyor.</Notice>}
          {p.topic && (
            <Text style={s.text}>
              {p.topic.label}:{' '}
              {p.topic.has_page ? (
                <Text style={s.link} onPress={() => router.push(`/topic/${p.topic!.pk}`)}>
                  {p.topic.title}
                </Text>
              ) : (
                `${p.topic.title} (silinmiş)`
              )}
            </Text>
          )}
          {p.details.map((d) => (
            <View key={d.label}>
              <Text style={s.label}>{d.label}</Text>
              <Text style={s.text} selectable>
                {d.value}
              </Text>
            </View>
          ))}
        </>
      )}
      <Text style={s.h2}>Oylama</Text>
      <Voting p={p} reload={reload} />
    </View>
  );
}

function ProposalView({ slug, pk }: { slug: string; pk: string }) {
  const [p, setP] = useState<Proposal | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setP(await api<Proposal>(`proposals/${slug}/${pk}/`)); // süresi dolduysa sunucu burada sonuçlandırır
      setError('');
    } catch (e) {
      setError(errorText(e));
    }
  }, [slug, pk]);

  useEffect(() => {
    load();
  }, [load]);

  if (!p) return <Status error={error} onRetry={load} />;
  return (
    <>
      <Stack.Screen options={{ title: p.kind }} />
      <CommentThread
        target={{ ct: p.ct, pk: p.pk }}
        onRefresh={load}
        header={
          <>
            {error ? <Notice tone="error">{error}</Notice> : null}
            <ProposalHeader p={p} reload={load} />
          </>
        }
      />
    </>
  );
}

export default function ProposalScreen() {
  const { slug, pk } = useLocalSearchParams<{ slug: string; pk: string }>();
  const { session } = useAuth();
  return <ProposalView key={session} slug={slug} pk={pk} />;
}

const useStyles = themed((c) => ({
  head: { gap: size.s2 },
  h1: { color: c.text, fontSize: 24, fontWeight: '800', lineHeight: 30 },
  h2: { color: c.text, fontSize: size.lg, fontWeight: '700', marginTop: size.s3 },
  text: { color: c.text, fontSize: 16, lineHeight: 24 },
  strong: { fontWeight: '800' },
  muted: { color: c.muted, fontSize: size.sm },
  label: { color: c.muted, fontSize: size.sm, fontWeight: '600' },
  link: { color: c.accent, textDecorationLine: 'underline' },
  voting: { gap: size.s2 },
  start: { alignSelf: 'flex-start' },
}));
