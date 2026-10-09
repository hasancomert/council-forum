// Yorum bölümü (comments/section.html): konu ve öneri ekranının tamamı bir FlatList; üstte içerik (header),
// sonra yorum formu ve ana yorumlar, yanıtları altlarında. Kaydırdıkça sonraki sayfa gelir.
import { router } from 'expo-router';
import { useState, type ReactElement } from 'react';
import { FlatList, RefreshControl, Text, TextInput, View } from 'react-native';

import { api, errorText, openSite, type Comment, type CommentPage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { usePaged } from '@/lib/paged';
import { size, themed, useColors } from '@/lib/theme';

import { ReportBox, VoteButtons } from './Vote';
import { Badge, Button, ConfirmBox, KeyboardArea, keyboardScroll, Notice, Row, Status } from './ui';

type Target = { ct: number; pk: number }; // yorumların bağlı olduğu konu ya da öneri

function CommentForm({ target, parent, onDone }: { target: Target; parent?: number; onDone: () => void }) {
  const s = useStyles();
  const c = useColors();
  const [body, setBody] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const send = async () => {
    setBusy(true);
    try {
      await api(`comments/${target.ct}/${target.pk}/`, { body, ...(parent && { parent }) });
      setBody('');
      setError('');
      onDone();
    } catch (e) {
      setError(errorText(e)); // boş/uzun yorum, hız sınırı, kapalı hedef
    } finally {
      setBusy(false);
    }
  };

  // Düğme kutunun sağında, alt kenarı hizalı: kutu klavyenin üstüne kayınca düğme de görünür. Kutu tek satırla
  // başlar, yazdıkça büyür (en fazla maxHeight, sonra kendi içinde kayar).
  return (
    <View style={s.form}>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <View style={s.composer}>
        <TextInput
          style={s.input}
          value={body}
          onChangeText={setBody}
          multiline
          placeholder={parent ? 'Yanıtın' : 'Yorumun'}
          placeholderTextColor={c.muted}
          accessibilityLabel={parent ? 'Yanıt' : 'Yorum'}
          autoFocus={!!parent}
        />
        <Button kind="primary" title={parent ? 'Yanıtla' : 'Yorum yaz'} onPress={send} disabled={busy || !body.trim()} />
      </View>
    </View>
  );
}

type Ctx = { target: Target; page: CommentPage; moderator: boolean; reload: () => void };

function CommentItem({ c, ctx, reply }: { c: Comment; ctx: Ctx; reply?: boolean }) {
  const s = useStyles();
  const [panel, setPanel] = useState<'reply' | 'delete' | 'report' | null>(null);
  const toggle = (p: typeof panel) => setPanel(panel === p ? null : p);
  const replies = c.replies.map((r) => <CommentItem key={r.pk} c={r} ctx={ctx} reply />);

  if (c.deleted || c.masked)
    return (
      <>
        <View style={[s.comment, reply && s.reply]}>
          <Text style={s.gone}>{c.deleted ? 'Bu yorum silindi.' : 'Bu yorum moderasyonla gizlendi.'}</Text>
        </View>
        {replies}
      </>
    );

  return (
    <>
      <View style={[s.comment, reply && s.reply]}>
        <Row>
          <Text style={s.author}>{c.author}</Text>
          <Text style={s.meta}>
            {c.created}
            {c.edited ? ' · düzenlendi' : ''}
          </Text>
          {c.hidden && <Badge label="Gizli" tone="danger" />}
        </Row>
        {c.hidden && <Notice>Moderasyonla gizlendi; metnini yalnızca yazarı ve yöneticiler görüyor.</Notice>}
        <Text style={s.body} selectable>
          {c.body}
        </Text>
        <Row style={s.actions}>
          <VoteButtons path={`comments/${c.pk}/vote/`} score={c.score!} mine={c.mine!} why={c.why!} />
          {!c.frozen && ctx.page.can_post && (
            <Button kind="small" title="Yanıtla" pressed={panel === 'reply'} onPress={() => toggle('reply')} />
          )}
          {c.own && <Button kind="small" title="Sil" pressed={panel === 'delete'} onPress={() => toggle('delete')} />}
          {ctx.moderator ? (
            <Button kind="small" title="Moderasyon" onPress={() => openSite(`/mod/${ctx.page.ct}/${c.pk}/`)} />
          ) : (
            c.can_report && (
              <Button kind="quiet" title="⚑" label="Şikayet et" pressed={panel === 'report'} onPress={() => toggle('report')} />
            )
          )}
        </Row>
        {panel === 'reply' && (
          <CommentForm
            target={ctx.target}
            parent={c.pk}
            onDone={() => {
              setPanel(null);
              ctx.reload();
            }}
          />
        )}
        {panel === 'delete' && (
          <ConfirmBox
            text="Silinen yorum geri alınamaz."
            action="Evet, sil"
            run={async () => {
              await api(`comments/${c.pk}/delete/`, {});
              ctx.reload();
            }}
          />
        )}
        {panel === 'report' && <ReportBox ct={ctx.page.ct} pk={c.pk} />}
      </View>
      {replies}
    </>
  );
}

/** header: konu ya da öneri; onRefresh: aşağı çekince onu da yenile. */
export function CommentThread({ target, header, onRefresh }: { target: Target; header: ReactElement; onRefresh: () => void }) {
  const s = useStyles();
  const c = useColors();
  const { me } = useAuth();
  const [sort, setSort] = useState('top');
  const list = usePaged<Comment, CommentPage>(`comments/${target.ct}/${target.pk}/?sort=${sort}`);
  const page = list.meta;
  // Yeni ana yorum "en yeni" sıralamasının başında görünür (sitedeki gibi); yanıttan sonra aynı sıralama yenilenir.
  const posted = () => (sort === 'new' ? list.reload() : setSort('new'));

  const form = !page ? null : !page.open ? (
    <Text style={s.meta}>Yorumlar kapalı.</Text>
  ) : page.can_post ? (
    <CommentForm target={target} onDone={posted} />
  ) : me ? (
    <Text style={s.meta}>Engelin sürerken yorum yazamazsın.</Text>
  ) : (
    <Button kind="chip" title="Yorum yazmak için giriş yap" onPress={() => router.push('/login')} style={s.start} />
  );

  return (
    <KeyboardArea>
      <FlatList
        data={list.items}
        keyExtractor={(item) => String(item.pk)}
        renderItem={({ item }) =>
          page && <CommentItem c={item} ctx={{ target, page, moderator: !!me?.moderator, reload: list.reload }} />
        }
        onEndReached={list.more}
        onEndReachedThreshold={0.5}
        {...keyboardScroll}
        contentContainerStyle={s.content}
        refreshControl={
          <RefreshControl
            refreshing={list.refreshing}
            onRefresh={() => {
              onRefresh();
              list.refresh();
            }}
            tintColor={c.accent}
          />
        }
        ListHeaderComponent={
          <View>
            {header}
            <Text style={s.h2}>Yorumlar{page ? ` (${page.count})` : ''}</Text>
            {form}
            {list.items.length > 0 && (
              <Row style={s.sorts}>
                <Text style={s.meta}>Sırala:</Text>
                <Button kind="chip" title="En çok oy" pressed={sort === 'top'} onPress={() => setSort('top')} />
                <Button kind="chip" title="En yeni" pressed={sort === 'new'} onPress={() => setSort('new')} />
              </Row>
            )}
          </View>
        }
        ListEmptyComponent={list.busy || list.error ? <Status error={list.error} onRetry={list.reload} /> : null}
        ListFooterComponent={list.items.length > 0 && list.busy ? <Status /> : null}
      />
    </KeyboardArea>
  );
}

const useStyles = themed((c) => ({
  content: { padding: size.s3, paddingBottom: size.s4 * 3 },
  h2: { color: c.text, fontSize: size.lg, fontWeight: '700', marginTop: size.s4, marginBottom: size.s2 },
  meta: { color: c.muted, fontSize: size.sm },
  start: { alignSelf: 'flex-start' },
  sorts: { marginTop: size.s3, marginBottom: size.s1 },
  form: { gap: size.s2, marginVertical: size.s2 },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: size.s2 },
  input: {
    flex: 1,
    minHeight: size.control + 4,
    maxHeight: 160,
    paddingHorizontal: 11,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: c.muted,
    borderRadius: size.radius,
    backgroundColor: c.surface,
    color: c.text,
    fontSize: 16,
    textAlignVertical: 'top',
  },
  comment: { paddingVertical: size.s3, borderTopWidth: 1, borderColor: c.line, gap: size.s2 },
  reply: { marginLeft: size.s4, paddingLeft: size.s3, borderTopWidth: 0, borderLeftWidth: 2, borderColor: c.accentLine },
  author: { color: c.text, fontWeight: '700', fontSize: size.sm },
  body: { color: c.text, fontSize: 16, lineHeight: 24 },
  gone: { color: c.muted, fontStyle: 'italic', fontSize: size.sm },
  actions: { gap: size.s1 },
}));
