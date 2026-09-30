import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';

import { Badge, Button, Notice, Row } from '@/components/ui';
import { openSite, SERVER } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { size, themed, useColors } from '@/lib/theme';

/** Sitede açılan sayfalar: hukuki metinler herkese, hesap işlemleri (tarayıcıda giriş ister) üyeye. */
function SiteLinks({ username }: { username?: string }) {
  const s = useStyles();
  return (
    <View style={s.section}>
      <Text style={s.h2}>Sitede</Text>
      <Row>
        {username && (
          <>
            <Button kind="chip" title="Şifreni değiştir" onPress={() => openSite('/accounts/password_change/')} />
            <Button
              kind="chip"
              title="Hakkındaki moderasyon kayıtları"
              onPress={() => openSite(`/mod/log/?user=${encodeURIComponent(username)}`)}
            />
            <Button kind="chip" title="Hesabı sil" onPress={() => openSite('/accounts/delete/')} />
          </>
        )}
        <Button kind="chip" title="Moderasyon kaydı" onPress={() => openSite('/mod/log/')} />
        <Button kind="chip" title="Kullanım şartları" onPress={() => openSite('/kullanim-sartlari/')} />
        <Button kind="chip" title="KVKK" onPress={() => openSite('/kvkk/')} />
      </Row>
      <Text style={s.muted}>Sunucu: {SERVER}</Text>
    </View>
  );
}

export default function Account() {
  const s = useStyles();
  const c = useColors();
  const { me, logout, refresh } = useAuth();
  const [refreshing, setRefreshing] = useState(false);

  // sekmeye her gelişte: rol (B statüsü oylaması), engel, açık öneri sayısı değişmiş olabilir
  useFocusEffect(
    useCallback(() => {
      refresh();
    }, [refresh]),
  );

  const pull = (
    <RefreshControl
      refreshing={refreshing}
      onRefresh={() => {
        setRefreshing(true);
        refresh().finally(() => setRefreshing(false));
      }}
      tintColor={c.accent}
    />
  );

  if (!me)
    return (
      <ScrollView contentContainerStyle={s.page}>
        <Text style={s.text}>Okumak için giriş gerekmez. Oy vermek, yorum yazmak ve öneri açmak için giriş yap.</Text>
        <Row>
          <Button kind="primary" title="Giriş yap" onPress={() => router.push('/login')} />
          <Button kind="chip" title="Kayıt ol" onPress={() => openSite('/accounts/signup/')} />
        </Row>
        <SiteLinks />
      </ScrollView>
    );

  return (
    <ScrollView contentContainerStyle={s.page} refreshControl={pull}>
      <Row>
        <Text style={s.name}>{me.username}</Text>
        {me.moderator && <Badge label="Yönetici" tone="pending" />}
      </Row>
      <Text style={s.muted}>Takma adın herkese açık; adın, soyadın ve e-postan kimseye gösterilmez.</Text>
      <View style={s.list}>
        <Text style={s.text}>
          Rol: <Text style={s.strong}>{me.role_label}</Text> · karar oylamalarında oy ağırlığın {me.weight}
        </Text>
        <Text style={s.text}>Kayıt: {me.joined}</Text>
        <Text style={s.text}>
          Açık önerilerin: {me.open_proposals}/{me.max_open_proposals}
        </Text>
      </View>
      {me.banned_until ? (
        <Notice tone="error">
          {me.banned_until} tarihine kadar engellisin: okuyabilir, kendi yorumunu silebilirsin; yazamaz, oy veremez, öneri
          açamazsın.
        </Notice>
      ) : me.can_vote ? (
        <Notice tone="ok">Oy hakkın var: karar oylamaları, ▲/▼, öneri ve şikayet.</Notice>
      ) : (
        <Notice>
          {me.why}. Oy hakkın {me.vote_from} tarihinde başlar; o zamana kadar okuyup yorum yazabilirsin.
        </Notice>
      )}
      {me.role === 'A' && me.can_vote && (
        <Button kind="chip" title="Bilirkişilik başvurusu" onPress={() => router.push('/new/expert')} style={s.start} />
      )}
      <Button title="Çıkış yap" onPress={logout} style={s.start} />
      <SiteLinks username={me.username} />
    </ScrollView>
  );
}

const useStyles = themed((c) => ({
  page: { padding: size.s4, gap: size.s3 },
  name: { color: c.text, fontSize: size.xl, fontWeight: '800' },
  text: { color: c.text, fontSize: 16, lineHeight: 24 },
  strong: { fontWeight: '700' },
  muted: { color: c.muted, fontSize: size.sm },
  list: { gap: size.s1 },
  start: { alignSelf: 'flex-start' },
  section: { gap: size.s2, marginTop: size.s3 },
  h2: {
    color: c.muted,
    fontSize: size.xs,
    fontWeight: '800',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
}));
