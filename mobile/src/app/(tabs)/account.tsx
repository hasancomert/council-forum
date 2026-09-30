import { router } from 'expo-router';
import { ScrollView, Text } from 'react-native';

import { Button, Row } from '@/components/ui';
import { openSite } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { size, themed } from '@/lib/theme';

export default function Account() {
  const s = useStyles();
  const { me, logout } = useAuth();
  if (!me)
    return (
      <ScrollView contentContainerStyle={s.page}>
        <Text style={s.text}>Oy vermek, yorum yazmak ve öneri açmak için giriş yap.</Text>
        <Row>
          <Button kind="primary" title="Giriş yap" onPress={() => router.push('/login')} />
          <Button kind="chip" title="Kayıt ol" onPress={() => openSite('/accounts/signup/')} />
        </Row>
      </ScrollView>
    );
  return (
    <ScrollView contentContainerStyle={s.page}>
      <Text style={s.name}>{me.username}</Text>
      <Text style={s.text}>
        {me.role_label} · karar oylamalarında oy ağırlığın {me.weight}
      </Text>
      <Button title="Çıkış yap" onPress={logout} />
    </ScrollView>
  );
}

const useStyles = themed((c) => ({
  page: { padding: size.s4, gap: size.s3 },
  name: { color: c.text, fontSize: size.xl, fontWeight: '800' },
  text: { color: c.text, fontSize: 16, lineHeight: 24 },
}));
