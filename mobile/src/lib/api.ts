import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';
import { Linking, Platform } from 'react-native';

// Django sunucusu: Expo Go'nun bağlandığı bilgisayar (hostUri "192.168.1.5:8081") ve 8000 portu.
// Başka bir adres gerekirse: EXPO_PUBLIC_SERVER=http://ADRES:8000 npx expo start
const host = Constants.expoConfig?.hostUri?.split(':')[0] || 'localhost';
export const SERVER = process.env.EXPO_PUBLIC_SERVER || `http://${host}:8000`;

/** Sitenin bir sayfasını tarayıcıda açar: kayıt, e-posta doğrulaması, şifre işlemleri (CAPTCHA ve e-posta
 *  bağlantısı tarayıcıda çalışır), moderasyon. */
export const openSite = (path: string) => Linking.openURL(`${SERVER}${path}`);

// Jeton telefonda şifreli depoda (iOS Keychain, Android Keystore); web önizlemesinde SecureStore yok: localStorage.
const KEY = 'forum-token';
const store =
  Platform.OS === 'web'
    ? {
        get: async () => localStorage.getItem(KEY),
        set: async (v: string | null) => (v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY)),
      }
    : {
        get: () => SecureStore.getItemAsync(KEY),
        set: (v: string | null) => (v ? SecureStore.setItemAsync(KEY, v) : SecureStore.deleteItemAsync(KEY)),
      };

let token: string | null = null;
let sessionEnded = () => {};

export const hasToken = () => token !== null;

export async function loadToken() {
  token = await store.get();
}

export async function setToken(value: string | null) {
  token = value;
  await store.set(value);
}

/** Jeton geçersiz olunca (şifre değişti, süresi doldu, hesap kapandı) çağrılır: oturum düşer. */
export function onSessionEnd(fn: () => void) {
  sessionEnded = fn;
}

export class ApiError extends Error {
  constructor(message: string, public status = 0, public errors: Record<string, string[]> = {}) {
    super(message);
  }
}

/** /api/<path>: body verilirse JSON POST, yoksa GET. Hata mesajı sunucudan (Türkçe) gelir. */
export async function api<T>(path: string, body?: object): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${SERVER}/api/${path}`, {
      method: body ? 'POST' : 'GET',
      headers: {
        ...(body && { 'Content-Type': 'application/json' }),
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: body && JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      `Sunucuya ulaşılamadı (${SERVER}). Sunucu "python manage.py runserver 0.0.0.0:8000" ile çalışıyor mu, ` +
        'telefon ve bilgisayar aynı ağda mı?',
    );
  }
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && token) {
    await setToken(null);
    sessionEnded();
  }
  if (!r.ok) throw new ApiError(data.error ?? `Sunucu hatası (${r.status})`, r.status, data.errors);
  return data as T;
}

export const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

// Yanıt tipleri: api/views.py'deki sözlükler.

export type Me = {
  username: string;
  role: 'A' | 'B';
  role_label: string;
  weight: number;
  can_post: boolean;
  can_vote: boolean;
  why: string; // oy verilemiyorsa nedeni
  banned_until: string | null;
  joined: string;
  vote_from: string;
  moderator: boolean;
  open_proposals: number;
  max_open_proposals: number;
};

export type Paged<T> = { results: T[]; page: number; pages: number };

export type Ref = { pk: number; title: string; has_page: boolean; label: string };
export type Pending = { label: string; slug: string; pk: number };

export type TopicRow = {
  pk: number;
  title: string;
  parent: Ref | null;
  score: number;
  comments: number;
  subs: number;
  created: string;
  locked: boolean;
  closed: boolean;
  pending: Pending[];
};

export type TopicList = Paged<TopicRow> & {
  tab: string;
  sort: string;
  tabs: [string, string][];
  sorts: [string, string][];
  parent: Ref | null;
};

export type Topic = {
  pk: number;
  ct: number; // içerik tipi: yorum ve şikayet adreslerinde
  title: string;
  description: string;
  masked: boolean; // gizli ve ben sahibi/yönetici değilim: metin yok
  hidden: boolean; // gizli ama ben görebiliyorum
  author: string;
  created: string;
  score: number;
  mine: -1 | 0 | 1;
  why: string; // ▲/▼ verilemiyorsa nedeni
  locked: boolean;
  open: boolean;
  parent: Ref | null;
  pending: Pending[];
  can_report: boolean;
  actions: [string, string][]; // [öneri tipi, bağlantı adı]
  subs: TopicRow[];
  n_subs: { open: number; closed: number } | null;
};

type Shown = {
  author: string;
  body: string;
  created: string;
  edited: boolean;
  hidden: boolean; // gizli ama ben görebiliyorum (yazarı ya da yönetici)
  score: number;
  mine: -1 | 0 | 1;
  why: string;
  frozen: boolean; // hedef kapalı ya da yorum gizli: yanıt ve oy yok
  own: boolean;
  can_report: boolean;
};

/** Silinen ya da başkasına gizli yorumda (deleted/masked) metin, yazar ve oy alanları gelmez. */
export type Comment = { pk: number; deleted: boolean; masked: boolean; replies: Comment[] } & Partial<Shown>;

export type CommentPage = Paged<Comment> & { count: number; open: boolean; can_post: boolean; ct: number; sort: string };

export type ProposalItem = {
  slug: string;
  pk: number;
  kind: string;
  title: string;
  discussion: boolean; // istek tartışmada: henüz oylanmaz
  left: string; // evresinin bitişine kalan süre
  participants: number;
  voted: boolean | null; // null: oy hakkım yok ya da giriş yok
};

export type Proposal = {
  slug: string;
  pk: number;
  ct: number;
  kind: string;
  title: string;
  masked: boolean;
  hidden: boolean;
  proposer: string;
  created: string;
  topic: Ref | null;
  details: { label: string; value: string }[];
  status: 'voting' | 'accepted' | 'rejected' | 'applied' | 'failed' | 'cancelled';
  status_label: string;
  discussion_ends: string | null; // tartışmadaysa oylamanın başlangıcı
  ends: string;
  left: string;
  turnout: { n: number; quorum: number } | null; // kural 6: oylama sürerken yalnızca katılım
  result: { yes: number; no: number; count: number; quorum: number; weighted: boolean; applied: string | null } | null;
  accepts: boolean;
  mine: 'yes' | 'no' | null;
  why: string;
  can_report: boolean;
};

export type Field = {
  name: string;
  label: string;
  help: string;
  required: boolean;
  type: 'line' | 'text' | 'choice';
  choices: [string, string][];
  max_length: number | null;
  initial: string;
};

export type ProposalForm = { title: string; target: string | null; fields: Field[] };
