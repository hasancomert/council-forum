import { useLocalSearchParams } from 'expo-router';

import { TopicList } from '@/components/TopicList';

/** Bir ana konunun alt konuları (konu ekranındaki "Tüm alt konular" ve "Kapalı alt konular"). */
export default function Subtopics() {
  const { pk, tab } = useLocalSearchParams<{ pk: string; tab?: string }>();
  return <TopicList parent={pk} tab={tab} />;
}
