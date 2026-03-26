// mobile/components/ChatInput.jsx
import React, { useState } from 'react';
import {
  View, TextInput, TouchableOpacity,
  Text, StyleSheet, ActivityIndicator
} from 'react-native';

const ORANGE = '#FF6B35';

export default function ChatInput({ onSend, loading }) {
  const [text, setText] = useState('');

  const handleSend = () => {
    if (!text.trim() || loading) return;
    onSend(text.trim());
    setText('');
  };

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.input}
        value={text}
        onChangeText={setText}
        placeholder="Ask anything: alarm, email, search..."
        placeholderTextColor="#555"
        multiline
        maxLength={500}
        returnKeyType="send"
        blurOnSubmit={false}
        onSubmitEditing={handleSend}
        editable={!loading}
      />
      <TouchableOpacity
        style={[styles.btn, (!text.trim() || loading) && styles.btnDisabled]}
        onPress={handleSend}
        disabled={!text.trim() || loading}
      >
        {loading
          ? <ActivityIndicator size="small" color="#000" />
          : <Text style={styles.btnText}>Send</Text>
        }
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    paddingHorizontal: 12,
    paddingTop: 10,
    paddingBottom: 12,
    backgroundColor: '#0d0d0d',
    borderTopWidth: 1,
    borderTopColor: '#1f1f1f',
    alignItems: 'flex-end',
  },
  input: {
    flex: 1,
    backgroundColor: '#161616',
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: '#fff',
    maxHeight: 110,
    marginRight: 8,
    borderWidth: 1,
    borderColor: '#2f2f2f',
    lineHeight: 20,
  },
  btn: {
    backgroundColor: ORANGE,
    borderRadius: 14,
    minWidth: 64,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  btnDisabled: { backgroundColor: '#6d331f' },
  btnText: { color: '#000', fontWeight: '800', fontSize: 14, letterSpacing: 0.3 },
});
