import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

const ORANGE = '#FF6B35';

const getVariant = (message, isUser) => {
  if (isUser) return 'user';
  if (message.type === 'error') return 'error';
  if (message.type === 'task_update') return 'task';
  if (message.actions_taken?.length) return 'tool';
  return 'assistant';
};

const sanitizeText = (content = '') =>
  content
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

const getBadgeLabel = (variant) => {
  if (variant === 'task') return 'TASK UPDATE';
  if (variant === 'tool') return 'TOOLS';
  if (variant === 'error') return 'ERROR';
  return 'ASSISTANT';
};

const formatTime = (timestamp) => {
  const parsed = timestamp ? new Date(timestamp) : null;
  if (!parsed || Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
  });
};

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const variant = getVariant(message, isUser);
  const text = sanitizeText(message.content || '');

  return (
    <View style={[styles.row, isUser ? styles.rowRight : styles.rowLeft]}>
      {!isUser && (
        <View style={[styles.avatar, variant === 'error' && styles.avatarError]}>
          <Text style={styles.avatarText}>PA</Text>
        </View>
      )}

      <View style={[styles.bubble, styles[`${variant}Bubble`]]}>
        {!isUser && (
          <Text style={[styles.badge, styles[`${variant}Badge`]]}>{getBadgeLabel(variant)}</Text>
        )}

        <Text style={[styles.text, styles[`${variant}Text`]]} selectable>
          {text}
        </Text>

        {message.actions_taken?.length > 0 && (
          <View style={styles.actions}>
            {message.actions_taken.map((action, index) => (
              <Text key={`${action.tool}_${index}`} style={styles.actionTag}>
                {action.tool}
              </Text>
            ))}
          </View>
        )}

        <Text style={styles.time}>{formatTime(message.timestamp)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', marginVertical: 6, paddingHorizontal: 12 },
  rowRight: { justifyContent: 'flex-end' },
  rowLeft: { justifyContent: 'flex-start' },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: ORANGE,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
    alignSelf: 'flex-end',
  },
  avatarError: { backgroundColor: '#ef4444' },
  avatarText: { color: '#000', fontSize: 10, fontWeight: '800' },
  bubble: { maxWidth: '84%', borderRadius: 16, paddingHorizontal: 12, paddingVertical: 10 },
  userBubble: { backgroundColor: ORANGE, borderBottomRightRadius: 4 },
  assistantBubble: { backgroundColor: '#1a1a1a', borderBottomLeftRadius: 4, borderWidth: 1, borderColor: '#2e2e2e' },
  toolBubble: { backgroundColor: '#15120f', borderBottomLeftRadius: 4, borderWidth: 1, borderColor: '#4a2d1b' },
  taskBubble: { backgroundColor: '#101612', borderBottomLeftRadius: 4, borderWidth: 1, borderColor: '#1f6b3a' },
  errorBubble: { backgroundColor: '#1b1010', borderBottomLeftRadius: 4, borderWidth: 1, borderColor: '#7f1d1d' },
  badge: {
    fontSize: 10,
    fontWeight: '700',
    marginBottom: 6,
    letterSpacing: 0.5,
    alignSelf: 'flex-start',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 2,
    overflow: 'hidden',
  },
  assistantBadge: { color: '#9ca3af', backgroundColor: '#242424' },
  toolBadge: { color: '#fb923c', backgroundColor: '#2a1d14' },
  taskBadge: { color: '#86efac', backgroundColor: '#173120' },
  errorBadge: { color: '#fca5a5', backgroundColor: '#3a1818' },
  text: { fontSize: 15, lineHeight: 22 },
  userText: { color: '#000', fontWeight: '600' },
  assistantText: { color: '#f8f8f8' },
  toolText: { color: '#ffe7d6' },
  taskText: { color: '#dbfce7' },
  errorText: { color: '#fee2e2' },
  actions: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 8, gap: 4 },
  actionTag: {
    fontSize: 11,
    backgroundColor: '#2a1a10',
    color: ORANGE,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#994a22',
  },
  time: { fontSize: 10, color: '#6b7280', marginTop: 6, alignSelf: 'flex-end' },
});
