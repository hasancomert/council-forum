// Ortak arayüz parçaları; görünüm static/css/site.css'teki sınıflarla aynı (.button, .primary, .chip, .badge, .notice).
import { useEffect, useState, type ReactNode } from 'react';
import {
  ActivityIndicator,
  Dimensions,
  Keyboard,
  Platform,
  Pressable,
  Text,
  View,
  type StyleProp,
  type ViewProps,
  type ViewStyle,
} from 'react-native';

import { errorText } from '@/lib/api';
import { size, themed, useColors } from '@/lib/theme';

// Dokunma hedefi en az 44px: görünen boyut küçük, hitSlop kenarlardan taşar (sitedeki görünmez ::after).
const slop = 4;

type ButtonProps = {
  title: string;
  onPress: () => void;
  kind?: 'plain' | 'primary' | 'chip' | 'small' | 'quiet'; // small: çerçevesiz (.actions), quiet: gri (şikayet)
  pressed?: boolean; // verilen oy / seçili seçenek: dolgulu (aria-pressed)
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  label?: string; // ekran okuyucu adı (simgeli düğme)
};

export function Button({ title, onPress, kind = 'plain', pressed, disabled, style, label }: ButtonProps) {
  const s = useStyles();
  const bare = kind === 'small' || kind === 'quiet';
  const filled = kind === 'primary' || (pressed && !bare); // çerçevesizde açık olan işlem açık mavi zeminli
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      hitSlop={slop}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled, selected: pressed }}
      style={({ pressed: down }) => [
        s.button,
        kind === 'chip' && s.chip,
        bare && s.small,
        bare && pressed && s.open,
        filled && s.filled,
        disabled && s.disabled,
        down && s.down,
        style,
      ]}>
      <Text
        style={[
          s.buttonText,
          (kind === 'chip' || kind === 'small') && s.chipText,
          kind === 'quiet' && s.quietText,
          filled && s.filledText,
        ]}>
        {title}
      </Text>
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

/** Sil, şikayet et gibi geri alınamayan işlemin onayı (sitedeki açılır <details> formu). run bir mesaj
 *  döndürürse (ör. "Şikayetin iletildi") yeşil kutuda gösterilir; hata kırmızı kutuda. */
export function ConfirmBox({ text, action, run }: { text: string; action: string; run: () => Promise<string | void> }) {
  const s = useStyles();
  const [result, setResult] = useState<{ text: string; ok: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  if (result) return <Notice tone={result.ok ? 'ok' : 'error'}>{result.text}</Notice>;
  const confirm = async () => {
    setBusy(true);
    try {
      const message = await run();
      if (message) setResult({ text: message, ok: true });
    } catch (e) {
      setResult({ text: errorText(e), ok: false });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Row style={s.confirm}>
      <Text style={s.muted}>{text}</Text>
      <Button title={action} onPress={confirm} disabled={busy} />
    </Row>
  );
}

/** Yazı kutusu olan kaydırmalı ekranın sarmalayıcısı: klavye açılınca odaktaki kutu klavyenin hemen üstüne kayar,
 *  içerik klavye açıkken de kaydırılır. Android'de uygulama ekranın tamamına çizildiği (edge-to-edge) için ekran
 *  klavyeyle küçülmez: alta klavye kadar boşluk konur, kaydırma alanı küçülür ve Android odaktaki kutuyu kendisi
 *  görünür alana kaydırır (ScrollView.onSizeChanged). iOS'ta bu işi kaydırma alanının
 *  automaticallyAdjustKeyboardInsets'i yapar ({...keyboardScroll}). */
export function KeyboardArea({ children }: { children: ReactNode }) {
  const [bottom, setBottom] = useState(0);
  useEffect(() => {
    if (Platform.OS !== 'android') return;
    const show = Keyboard.addListener('keyboardDidShow', (e) =>
      // ekranın altından klavyenin üst kenarına (endCoordinates.height gezinme çubuğunu saymaz)
      setBottom(Math.max(0, Dimensions.get('screen').height - e.endCoordinates.screenY)),
    );
    const hide = Keyboard.addListener('keyboardDidHide', () => setBottom(0));
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);
  return <View style={{ flex: 1, paddingBottom: bottom }}>{children}</View>;
}

/** KeyboardArea içindeki kaydırma alanına (ScrollView, FlatList): iOS'ta klavye kadar alt boşluk ve odaktaki kutuyu
 *  klavyenin üstüne kaydırma; dokunuş klavyeyi kapatmadan düğmeye gider. */
export const keyboardScroll = { automaticallyAdjustKeyboardInsets: true, keyboardShouldPersistTaps: 'handled' } as const;

export function Row({ children, style, ...rest }: ViewProps) {
  return (
    <View style={[{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: size.s2 }, style]} {...rest}>
      {children}
    </View>
  );
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
  small: { minHeight: size.chip, paddingHorizontal: 10, borderWidth: 0, backgroundColor: 'transparent' },
  open: { backgroundColor: c.accentSoft },
  quietText: { color: c.muted, fontSize: 15 },
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
  confirm: { marginVertical: size.s2 },
  muted: { color: c.muted, fontSize: size.sm },
}));
