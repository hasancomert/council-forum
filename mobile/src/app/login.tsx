import { router } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, TextInput } from 'react-native';

import { Button, Notice, Row } from '@/components/ui';
import { errorText, openSite, SERVER } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { size, themed, useColors } from '@/lib/theme';

export default function Login() {
  const s = useStyles();
  const c = useColors();
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await login(username.trim(), password);
      if (router.canGoBack()) router.back();
      else router.replace('/');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView style={s.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={s.card} keyboardShouldPersistTaps="handled">
        {error ? <Notice tone="error">{error}</Notice> : null}
        <Text style={s.label}>Takma ad</Text>
        <TextInput
          style={s.input}
          value={username}
          onChangeText={setUsername}
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="username"
          textContentType="username"
          placeholderTextColor={c.muted}
          returnKeyType="next"
        />
        <Text style={s.label}>Şifre</Text>
        <TextInput
          style={s.input}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="current-password"
          textContentType="password"
          returnKeyType="go"
          onSubmitEditing={submit}
        />
        <Button kind="primary" title={busy ? 'Giriş yapılıyor…' : 'Giriş yap'} onPress={submit} disabled={busy} />
        <Row style={s.links}>
          <Button kind="chip" title="Kayıt ol" onPress={() => openSite('/accounts/signup/')} />
          <Button kind="chip" title="Şifremi unuttum" onPress={() => openSite('/accounts/password_reset/')} />
        </Row>
        <Text style={s.small}>Kayıt ve şifre işlemleri sitede açılır. Sunucu: {SERVER}</Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const useStyles = themed((c) => ({
  fill: { flex: 1 },
  card: { padding: size.s4, gap: size.s2 },
  label: { color: c.text, fontSize: 15, fontWeight: '600', marginTop: size.s2 },
  input: {
    minHeight: size.control + 4,
    paddingHorizontal: 11,
    borderWidth: 1,
    borderColor: c.muted,
    borderRadius: size.radius,
    backgroundColor: c.surface,
    color: c.text,
    fontSize: 16,
  },
  links: { marginTop: size.s3 },
  small: { color: c.muted, fontSize: size.sm, marginTop: size.s3 },
}));
