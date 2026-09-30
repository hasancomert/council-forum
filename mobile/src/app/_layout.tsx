import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useColorScheme } from 'react-native';

import { AuthProvider } from '@/lib/auth';
import { useColors } from '@/lib/theme';

export default function RootLayout() {
  const c = useColors();
  const base = useColorScheme() === 'dark' ? DarkTheme : DefaultTheme;
  // Başlık, sekme çubuğu ve zemin renkleri sitedeki gibi
  const theme = {
    ...base,
    colors: { ...base.colors, primary: c.accent, background: c.bg, card: c.surface, text: c.text, border: c.line },
  };
  return (
    <ThemeProvider value={theme}>
      <AuthProvider>
        <StatusBar style="auto" />
        <Stack screenOptions={{ headerBackTitle: 'Geri' }}>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="login" options={{ title: 'Giriş yap', presentation: 'modal' }} />
          <Stack.Screen name="topic/[pk]" options={{ title: 'Konu' }} />
          <Stack.Screen name="subtopics/[pk]" options={{ title: 'Alt konular' }} />
        </Stack>
      </AuthProvider>
    </ThemeProvider>
  );
}
