// ▲ puan ▼ (konu ve yorum; templates/_vote.html) ve şikayet.
import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { api, errorText } from '@/lib/api';
import { size, themed } from '@/lib/theme';

import { ConfirmBox, Row } from './ui';

type Props = { path: string; score: number; mine: number; why: string };

/** path: oy adresi (topics/<pk>/vote/, comments/<pk>/vote/). why doluysa oy verilemez: düğmeler soluk,
 *  basınca nedeni yazar (sitede fareyle üzerine gelince görünen title). Aynı tuşa ikinci basış oyu geri alır. */
export function VoteButtons({ path, score, mine, why }: Props) {
  const s = useStyles();
  const [state, setState] = useState({ score, mine });
  const [prev, setPrev] = useState({ score, mine });
  const [hint, setHint] = useState('');
  if (prev.score !== score || prev.mine !== mine) {
    // sayfa yenilendi: sunucunun değeri geçerli (React'in "prop değişince state'i ayarla" kalıbı)
    setPrev({ score, mine });
    setState({ score, mine });
  }

  const vote = async (value: 1 | -1) => {
    if (why) return setHint(why);
    try {
      setState(await api<{ score: number; mine: number }>(path, { value }));
      setHint('');
    } catch (e) {
      setHint(errorText(e));
    }
  };

  const key = (value: 1 | -1, glyph: string, label: string) => (
    <Pressable
      onPress={() => vote(value)}
      hitSlop={4}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={why || undefined}
      accessibilityState={{ selected: state.mine === value, disabled: !!why }}
      style={[s.key, state.mine === value && s.on, !!why && s.blocked]}>
      <Text style={[s.glyph, state.mine === value && s.glyphOn]}>{glyph}</Text>
    </Pressable>
  );

  return (
    <View>
      <Row style={s.row}>
        {key(1, '▲', 'Artı oy')}
        <Text style={s.score} accessibilityLabel={`puan ${state.score}`}>
          {state.score}
        </Text>
        {key(-1, '▼', 'Eksi oy')}
      </Row>
      {hint ? <Text style={s.hint}>{hint}</Text> : null}
    </View>
  );
}

/** Şikayet: kimlik gizli, içerik kendiliğinden gizlenmez (yöneticinin kuyruğuna düşer). */
export function ReportBox({ ct, pk }: { ct: number; pk: number }) {
  return (
    <ConfirmBox
      text="Yöneticilere iletilir; kimliğin gizli kalır."
      action="Şikayet et"
      run={async () => (await api<{ message: string }>(`report/${ct}/${pk}/`, {})).message}
    />
  );
}

const useStyles = themed((c) => ({
  row: { gap: size.s1 },
  key: {
    width: size.chip,
    height: size.chip,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: c.line,
    borderRadius: size.radius,
    backgroundColor: c.surface,
  },
  on: { borderColor: c.accent, backgroundColor: c.accent },
  blocked: { opacity: 0.45 },
  glyph: { color: c.text, fontSize: 14 },
  glyphOn: { color: c.accentText },
  score: { minWidth: 22, color: c.text, fontWeight: '800', textAlign: 'center', fontVariant: ['tabular-nums'] },
  hint: { color: c.muted, fontSize: size.xs, marginTop: 2 },
}));
