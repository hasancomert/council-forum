import { Tabs } from 'expo-router/js-tabs';
import { Text, type ColorValue } from 'react-native';

// Simgeler yazı karakteri: ek paket (ikon yazı tipi) gerekmez.
const icon = (glyph: string) =>
  function TabIcon({ color }: { color: ColorValue }) {
    return <Text style={{ color, fontSize: 20 }}>{glyph}</Text>;
  };

export default function TabLayout() {
  return (
    <Tabs screenOptions={{ headerTitleStyle: { fontWeight: '800' } }}>
      <Tabs.Screen name="index" options={{ title: 'Konular', tabBarIcon: icon('☰') }} />
      <Tabs.Screen name="account" options={{ title: 'Hesabım', tabBarIcon: icon('◉') }} />
    </Tabs>
  );
}
