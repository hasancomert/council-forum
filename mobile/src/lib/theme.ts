import { StyleSheet, useColorScheme } from 'react-native';

// static/css/site.css'teki :root renkleri; koyu tema (prefers-color-scheme) yalnızca renkleri değiştirir.
const light = {
  bg: '#f7f7f5',
  surface: '#ffffff',
  text: '#1c1e22',
  muted: '#565d69',
  mutedSoft: '#eceef1',
  line: '#dde1e6',
  accent: '#1d5bb8',
  accentSoft: '#e8f0fb',
  accentLine: '#a5bfe6',
  accentText: '#ffffff',
  danger: '#b0241c',
  dangerSoft: '#fbe9e7',
  ok: '#1d6a34',
  okSoft: '#e6f3e9',
};

const dark: Colors = {
  bg: '#141619',
  surface: '#1c1f23',
  text: '#e7e9ec',
  muted: '#a4abb6',
  mutedSoft: '#2a2e35',
  line: '#353a42',
  accent: '#82b1ff',
  accentSoft: '#1c2a42',
  accentLine: '#3d5c90',
  accentText: '#0b1a33',
  danger: '#ff8a80',
  dangerSoft: '#3a1f1e',
  ok: '#80d99c',
  okSoft: '#173020',
};

export type Colors = typeof light;

// Boşluk, köşe ve yazı ölçüleri de site.css'teki gibi (1rem = 16).
export const size = { s1: 4, s2: 8, s3: 16, s4: 24, radius: 8, radiusLg: 14, control: 40, chip: 36, sm: 14, xs: 12, lg: 19, xl: 28 };

export function useColors(): Colors {
  return useColorScheme() === 'dark' ? dark : light;
}

/** Renklere bağlı stiller: `const useStyles = themed(c => ({...}))`, bileşende `const s = useStyles()`.
 *  Her tema için StyleSheet bir kez oluşturulur (iki tema, iki önbellek girdisi). */
export function themed<T extends StyleSheet.NamedStyles<T>>(make: (c: Colors) => T) {
  const cache = new Map<Colors, T>();
  return () => {
    const c = useColors();
    let styles = cache.get(c);
    if (!styles) cache.set(c, (styles = StyleSheet.create(make(c))));
    return styles;
  };
}
