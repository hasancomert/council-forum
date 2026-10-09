import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ScrollView, Text, TextInput, View } from 'react-native';

import { Button, KeyboardArea, keyboardScroll, Notice, Row, Status } from '@/components/ui';
import { api, ApiError, errorText, type Field, type ProposalForm } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { size, themed, useColors } from '@/lib/theme';

/** Formun bir alanı: tek satır, çok satır ya da seçenekler (sitedeki radyo düğmeleri gibi). */
function FieldInput({ f, value, onChange, errors }: { f: Field; value: string; onChange: (v: string) => void; errors?: string[] }) {
  const s = useStyles();
  const c = useColors();
  return (
    <View style={s.field}>
      <Text style={s.label}>{f.label}</Text>
      {f.help ? <Text style={s.help}>{f.help}</Text> : null}
      {f.type === 'choice' ? (
        <Row accessibilityRole="radiogroup">
          {f.choices.map(([v, label]) => (
            <Button key={v} kind="chip" title={label} pressed={value === v} onPress={() => onChange(v)} />
          ))}
        </Row>
      ) : (
        <TextInput
          style={[s.input, f.type === 'text' && s.multi]}
          value={value}
          onChangeText={onChange}
          multiline={f.type === 'text'}
          maxLength={f.max_length ?? undefined}
          autoCapitalize={f.name === 'username' ? 'none' : 'sentences'}
          accessibilityLabel={f.label}
          placeholderTextColor={c.muted}
        />
      )}
      {errors?.map((e) => (
        <Text key={e} style={s.error}>
          {e}
        </Text>
      ))}
    </View>
  );
}

/** Her öneri tipi için tek form: alanları, etiketleri ve başlangıç değerlerini sunucu verir (sitenin
 *  ModelForm'u); denetim de orada (modelin clean()'i: oy hakkı, açık öneri sınırı, aynı öneri, kapalı konu). */
export default function NewProposal() {
  const s = useStyles();
  const { slug, topic } = useLocalSearchParams<{ slug: string; topic?: string }>();
  const path = `proposals/new/${slug}/${topic ? `${topic}/` : ''}`;
  const { refresh } = useAuth();
  const [form, setForm] = useState<ProposalForm | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const f = await api<ProposalForm>(path);
      setForm(f);
      setValues(Object.fromEntries(f.fields.map((x) => [x.name, x.initial])));
      setError('');
    } catch (e) {
      setError(errorText(e));
    }
  }, [path]);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    setBusy(true);
    try {
      const d = await api<{ slug: string; pk: number }>(path, values);
      refresh(); // açık öneri sayısı
      router.replace(`/proposal/${d.slug}/${d.pk}`);
    } catch (e) {
      const fields = e instanceof ApiError ? e.errors : {};
      setErrors(Object.keys(fields).length ? fields : { __all__: [errorText(e)] });
    } finally {
      setBusy(false);
    }
  };

  if (!form) return <Status error={error} onRetry={load} />;
  return (
    <KeyboardArea>
      <ScrollView contentContainerStyle={s.page} {...keyboardScroll}>
        <Stack.Screen options={{ title: form.title }} />
        {form.target && (
          <Text style={s.text}>
            {form.target_label}: <Text style={s.strong}>{form.target}</Text>
          </Text>
        )}
        {errors.__all__ && <Notice tone="error">{errors.__all__.join(' ')}</Notice>}
        {form.fields.map((f) => (
          <FieldInput
            key={f.name}
            f={f}
            value={values[f.name] ?? ''}
            onChange={(v) => setValues({ ...values, [f.name]: v })}
            errors={errors[f.name]}
          />
        ))}
        <Text style={s.help}>Öneri açılınca oylamaya girer; sonuç süre bitince açıklanır.</Text>
        <Button kind="primary" title={busy ? 'Açılıyor…' : 'Öneriyi aç'} onPress={submit} disabled={busy} style={s.start} />
      </ScrollView>
    </KeyboardArea>
  );
}

const useStyles = themed((c) => ({
  page: { padding: size.s4, gap: size.s3, paddingBottom: size.s4 * 3 },
  text: { color: c.text, fontSize: 16 },
  strong: { fontWeight: '700' },
  field: { gap: 6 },
  label: { color: c.text, fontSize: 15, fontWeight: '600' },
  help: { color: c.muted, fontSize: size.sm },
  input: {
    minHeight: size.control + 4,
    paddingHorizontal: 11,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: c.muted,
    borderRadius: size.radius,
    backgroundColor: c.surface,
    color: c.text,
    fontSize: 16,
  },
  multi: { minHeight: 120, textAlignVertical: 'top' },
  error: { color: c.danger, fontSize: size.sm, fontWeight: '600' },
  start: { alignSelf: 'flex-start' },
}));
