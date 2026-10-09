import { Link, useNavigation } from 'expo-router';
import { useEffect } from 'react';
import { Text } from 'react-native';

import { TopicList } from '@/components/TopicList';
import { useAuth } from '@/lib/auth';
import { size, themed } from '@/lib/theme';

export default function Home() {
  const s = useStyles();
  const { me } = useAuth();
  const navigation = useNavigation();

  useEffect(() => {
    navigation.setOptions({
      headerRight: () =>
        !me && (
          <Link href="/login" style={s.headerLink}>
            Giriş yap
          </Link>
        ),
    });
  }, [navigation, me, s]);

  return (
    <TopicList
      header={<Text style={s.lead}>Burada kararları üyeler verir: konu açmak, düzenlemek ve kapatmak oylamayla olur.</Text>}
    />
  );
}

const useStyles = themed((c) => ({
  lead: { color: c.muted, fontSize: 15, marginBottom: size.s3 },
  headerLink: { color: c.accent, fontSize: 16, fontWeight: '700', paddingHorizontal: size.s3, paddingVertical: size.s2 },
}));
