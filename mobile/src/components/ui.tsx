// Ortak arayüz parçaları; görünüm static/css/site.css'teki sınıflarla aynı (.button, .primary, .chip, .badge, .notice).
import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, Text, View, type StyleProp, type ViewStyle } from 'react-native';

import { size, themed, useColors } from '@/lib/theme';

// Dokunma hedefi en az 44px: görünen boyut küçük, hitSlop kenarlardan taşar (sitedeki görünmez ::after).
const slop = 4;

type ButtonProps = {
  title: string;
  onPress: () => void;
  kind?: 'plain' | 'primary' | 'chip';
  pressed?: boolean; // verilen oy / seçili seçenek: dolgulu (aria-pressed)
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function Button({ title, onPress, kind = 'plain', pressed, disabled, style }: ButtonProps) {
  const s = useStyles();
  const filled = kind === 'primary' || pressed;
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      hitSlop={slop}
      accessibilityRole="button"
      accessibilityState={{ disabled, selected: pressed }}
      style={({ pressed: down }) => [
        s.button,
        kind === 'chip' && s.chip,
        filled && s.filled,
        disabled && s.disabled,
        down && s.down,
        style,
      ]}>
      <Text style={[s.buttonText, kind === 'chip' && s.chipText, filled && s.filledText]}>{title}</Text>
    </Pressable>
  );
}

type Tone = 'plain' | 'pending' | 'danger' | 'todo';

export function Badge({ label, tone = 'plain', onPress }: { label: string; tone?: Tone; onPress?: () => void }) {
  const s = useStyles();
  const badge = <Text style={[s.badge, s[tone]]}>{label}</Text>;
  return onPress ? (
    <Pressable onPress={onPress} hitSlop={slop} accessibilityRole="link">
      {badge}
    </Pressable>
  ) : (
    badge
  );
}

/** Uyarı kutusu (.notice): mavi, hata kırmızı, başarı yeşil. */
export function Notice({ children, tone }: { children: ReactNode; tone?: 'error' | 'ok' }) {
  const s = useStyles();
  return (
    <View style={[s.notice, tone === 'error' && s.noticeError, tone === 'ok' && s.noticeOk]}>
      <Text style={s.text}>{children}</Text>
    </View>
  );
}

/** Yükleniyor ya da hata (yeniden dene düğmesiyle). */
export function Status({ error, onRetry }: { error?: string; onRetry?: () => void }) {
  const s = useStyles();
  const c = useColors();
  if (!error) return <ActivityIndicator color={c.accent} style={s.status} />;
  return (
    <View style={s.status}>
      <Notice tone="error">{error}</Notice>
      {onRetry && <Button title="Yeniden dene" onPress={onRetry} />}
    </View>
  );
}

export function Row({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: size.s2 }, style]}>{children}</View>;
}

const useStyles = themed((c) => ({
  text: { color: c.text, fontSize: 16, lineHeight: 24 },
  button: {
    minHeight: size.control,
    paddingHorizontal: size.s3,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: c.line,
    borderRadius: size.radius,
    backgroundColor: c.surface,
  },
  buttonText: { color: c.text, fontSize: 16, fontWeight: '600' },
  chip: { minHeight: size.chip, paddingHorizontal: 13, borderColor: c.accentLine },
  chipText: { color: c.accent, fontSize: 15 },
  filled: { borderColor: c.accent, backgroundColor: c.accent },
  filledText: { color: c.accentText },
  disabled: { opacity: 0.45 },
  down: { transform: [{ translateY: 1 }] },
  badge: {
    alignSelf: 'flex-start',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 1,
    borderRadius: 99,
    fontSize: size.xs,
    fontWeight: '700',
    letterSpacing: 0.25,
  },
  plain: { backgroundColor: c.mutedSoft, color: c.muted },
  pending: { backgroundColor: c.accentSoft, color: c.accent },
  danger: { backgroundColor: c.dangerSoft, color: c.danger },
  todo: { backgroundColor: c.accent, color: c.accentText },
  notice: {
    marginBottom: size.s2,
    paddingVertical: size.s2,
    paddingHorizontal: size.s3,
    borderWidth: 1,
    borderLeftWidth: 4,
    borderColor: c.line,
    borderLeftColor: c.accent,
    borderRadius: size.radius,
    backgroundColor: c.accentSoft,
  },
  noticeError: { borderLeftColor: c.danger, backgroundColor: c.dangerSoft },
  noticeOk: { borderLeftColor: c.ok, backgroundColor: c.okSoft },
  status: { padding: size.s4, gap: size.s3, alignItems: 'center' },
}));
