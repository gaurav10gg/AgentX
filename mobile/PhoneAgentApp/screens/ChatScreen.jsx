import React, { useEffect, useRef, useState } from 'react';
import {
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StatusBar,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import MessageBubble from '../components/MessageBubble';
import ChatInput from '../components/ChatInput';
import { clearHistory, sendMessage } from '../services/api';
import { isConfigured, loadChatHistory, resetSession, saveChatHistory } from '../services/storage';
import { setAlarm, setupNotificationChannel } from '../services/alarm';

const ORANGE = '#FF6B35';

const QUICK_PROMPTS = [
  'Set alarm for 7 AM',
  'Kal subah 8 baje alarm lagao',
  'What are top AI startups in India?',
  'Send email to professor about leave',
];

const getErrorMessage = (error) => {
  if (error?.response?.data?.detail) {
    return String(error.response.data.detail);
  }
  if (error?.code === 'ECONNABORTED') {
    return 'Request timed out. Check backend speed or network.';
  }
  if (error?.message?.includes('Network Error')) {
    return 'Cannot reach backend. Check URL and ensure server is running.';
  }
  return 'Something went wrong. Please try again.';
};

const createMessage = (payload) => ({
  id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
  timestamp: new Date().toISOString(),
  ...payload,
});

export default function ChatScreen({ navigation }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const flatListRef = useRef(null);

  useEffect(() => {
    checkSetup();
    loadHistory();
    setupNotificationChannel();
  }, []);

  const persistAndSetMessages = async (nextMessages) => {
    setMessages(nextMessages);
    await saveChatHistory(nextMessages);
  };

  const checkSetup = async () => {
    const configured = await isConfigured();
    if (!configured) {
      navigation.navigate('Settings');
    }
  };

  const loadHistory = async () => {
    const history = await loadChatHistory();
    setMessages(history);
  };

  const buildTaskUpdateMessage = (notifications) => {
    if (!notifications?.length) return null;
    const lines = notifications.map((item) => `- ${item.description}: ${item.result}`);
    return createMessage({
      role: 'assistant',
      type: 'task_update',
      content: `Completed tasks:\n${lines.join('\n')}`,
    });
  };

  const handleSend = async (text) => {
    if (loading) return;

    const userMessage = createMessage({
      role: 'user',
      content: text,
    });

    const snapshot = [...messages, userMessage];
    await persistAndSetMessages(snapshot);
    setLoading(true);

    try {
      const response = await sendMessage(text);

      if (response.alarm_data) {
        await handleAlarm(response.alarm_data);
      }

      const updateMessage = buildTaskUpdateMessage(response.task_notifications);
      const assistantMessage = createMessage({
        role: 'assistant',
        content: response.reply,
        actions_taken: response.actions_taken || [],
        type: (response.actions_taken || []).length ? 'tool_result' : 'assistant',
      });

      const finalMessages = updateMessage
        ? [...snapshot, updateMessage, assistantMessage]
        : [...snapshot, assistantMessage];

      await persistAndSetMessages(finalMessages);
    } catch (error) {
      const errorMessage = createMessage({
        role: 'assistant',
        type: 'error',
        content: getErrorMessage(error),
      });
      const finalMessages = [...snapshot, errorMessage];
      await persistAndSetMessages(finalMessages);
    } finally {
      setLoading(false);
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 80);
    }
  };

  const handleAlarm = async (alarmData) => {
    try {
      const result = await setAlarm(
        alarmData.hour,
        alarmData.minute,
        alarmData.label || 'PhoneAgent Alarm'
      );

      const timeText = `${alarmData.hour.toString().padStart(2, '0')}:${alarmData.minute.toString().padStart(2, '0')}`;
      const scheduledText = result.scheduledFor ? new Date(result.scheduledFor).toLocaleString('en-IN') : '';

      Alert.alert(
        'Alarm Set',
        scheduledText ? `Alarm scheduled for ${timeText}\n${scheduledText}` : `Alarm scheduled for ${timeText}`,
        [{ text: 'OK' }]
      );
    } catch (error) {
      Alert.alert('Alarm Error', error.message || 'Could not set alarm');
    }
  };

  const handleClear = () => {
    Alert.alert('Clear Chat', 'Clear all messages and start fresh?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Clear',
        style: 'destructive',
        onPress: async () => {
          await clearHistory();
          await resetSession();
          await persistAndSetMessages([]);
        },
      },
    ]);
  };

  const renderEmptyState = () => (
    <View style={styles.empty}>
      <Text style={styles.emptyTitle}>PhoneAgent</Text>
      <Text style={styles.emptySubtitle}>Type once. The assistant executes the full flow.</Text>
      <Text style={styles.quickHint}>Try one of these:</Text>
      <View style={styles.suggestions}>
        {QUICK_PROMPTS.map((suggestion, index) => (
          <TouchableOpacity
            key={index}
            style={styles.suggestionChip}
            onPress={() => handleSend(suggestion)}
            disabled={loading}
          >
            <Text style={styles.suggestionText}>{suggestion}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      <StatusBar barStyle="light-content" backgroundColor="#000" />

      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>PhoneAgent</Text>
          <Text style={styles.headerSub}>Memory, tools, and automation</Text>
        </View>
        <View style={styles.headerActions}>
          <TouchableOpacity onPress={handleClear} style={styles.headerBtn}>
            <Text style={styles.headerBtnText}>Clear</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => navigation.navigate('Settings')} style={styles.headerBtn}>
            <Text style={styles.headerBtnText}>Settings</Text>
          </TouchableOpacity>
        </View>
      </View>

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={0}
      >
        {messages.length === 0 ? (
          renderEmptyState()
        ) : (
          <FlatList
            ref={flatListRef}
            data={messages}
            keyExtractor={(item) => item.id}
            renderItem={({ item }) => <MessageBubble message={item} />}
            contentContainerStyle={styles.messageList}
            onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
            keyboardShouldPersistTaps="handled"
            keyboardDismissMode="on-drag"
            showsVerticalScrollIndicator={false}
          />
        )}

        {loading && (
          <View style={styles.typingBar}>
            <Text style={styles.typingText}>Assistant is thinking...</Text>
          </View>
        )}

        <ChatInput onSend={handleSend} loading={loading} />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: '#000' },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a1a',
    backgroundColor: '#000',
  },
  headerTitle: { fontSize: 18, fontWeight: '800', color: '#fff' },
  headerSub: { fontSize: 11, color: ORANGE, marginTop: 1, letterSpacing: 0.4 },
  headerActions: { flexDirection: 'row', gap: 8 },
  headerBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: '#161616',
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#2d2d2d',
  },
  headerBtnText: { fontSize: 13, color: '#aaa', fontWeight: '600' },
  messageList: { paddingVertical: 12, paddingBottom: 20 },
  typingBar: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: '#0f0f0f',
    borderTopWidth: 1,
    borderTopColor: '#1f1f1f',
  },
  typingText: { color: '#7a7a7a', fontSize: 12, fontStyle: 'italic' },
  empty: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
  },
  emptyTitle: { fontSize: 30, fontWeight: '900', color: '#fff', marginBottom: 6 },
  emptySubtitle: { fontSize: 14, color: '#777', marginBottom: 10, textAlign: 'center', lineHeight: 20 },
  quickHint: { fontSize: 12, color: '#9a9a9a', marginBottom: 14, letterSpacing: 0.3, textTransform: 'uppercase' },
  suggestions: { width: '100%', gap: 10 },
  suggestionChip: {
    borderWidth: 1,
    borderColor: '#262626',
    borderRadius: 14,
    padding: 14,
    backgroundColor: '#101010',
  },
  suggestionText: { color: '#b2b2b2', fontSize: 14 },
});
