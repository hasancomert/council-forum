// Katılım çubuğu (voting/_turnout.html) ve bitmiş oylamanın sonuç çubuğu (progress.result). Satır içi genişlik
// yüzdeyle; sitedeki <progress>'in karşılığı.
import { Text, View } from 'react-native';

import { size, themed } from '@/lib/theme';

/** Kural 6 gereği evet/hayır değil, yeter sayıya ilerleme (kural 3). */
export function Turnout({ n, quorum, left }: { n: number; quorum: number; left?: string }) {
  const s = useStyles();
  const met = n >= quorum;
  return (
    <View style={s.turnout} accessibilityLabel={`Yeter sayıya ilerleme: ${n}/${quorum}`}>
      <View style={s.track}>
        <View style={[s.fill, met && s.met, { width: `${Math.min(100, (100 * n) / quorum)}%` }]} />
      </View>
      <Text style={[s.small, met && s.metText]}>
        {n}/{quorum} katılım{met ? ' · yeter sayı tamam' : ''}
        {left ? ` · ${left} kaldı` : ''}
      </Text>
    </View>
  );
}

/** Yeşil evet, kırmızı hayır (ağırlıklı toplamlar). */
export function ResultBar({ yes, no }: { yes: number; no: number }) {
  const s = useStyles();
  return (
    <View style={[s.track, s.result]} accessibilityLabel={`Evet ${yes}, hayır ${no}`}>
      <View style={[s.fill, s.yes, { width: `${(100 * yes) / (yes + no)}%` }]} />
    </View>
  );
}

const useStyles = themed((c) => ({
  turnout: { gap: 3, marginTop: 6, maxWidth: 384 },
  track: { height: 7, borderRadius: 99, backgroundColor: c.mutedSoft, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 99, backgroundColor: c.accent },
  met: { backgroundColor: c.ok },
  small: { color: c.muted, fontSize: size.sm },
  metText: { color: c.ok, fontWeight: '700' },
  result: { height: 10, maxWidth: 384, marginVertical: size.s2, backgroundColor: c.danger, borderRadius: 0 },
  yes: { backgroundColor: c.ok, borderRadius: 0 },
}));
