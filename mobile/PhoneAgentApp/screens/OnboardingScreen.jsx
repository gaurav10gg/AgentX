// mobile/screens/OnboardingScreen.jsx
import React, { useState } from 'react';
import { Platform, StatusBar } from 'react-native';
import {
  View, Text, StyleSheet, TouchableOpacity,
  TextInput, SafeAreaView, Alert, ActivityIndicator,
  Linking, ScrollView
} from 'react-native';
import { saveProviderSettings } from '../services/storage';
import { checkBackendHealth, getGoogleLoginUrl } from '../services/api';

const ORANGE = '#FF6B35';

const STEPS = [
  {
    id: 'welcome',
    title: 'PhoneAgent',
    subtitle: 'Your AI assistant for Android.\nPowered by Sarvam AI — Made in India.',
    hint: null,
  },
  {
    id: 'backend',
    title: 'Start the Backend',
    subtitle: 'Run this on your laptop:',
    hint: 'uvicorn server:app --reload',
  },
  {
    id: 'apikey',
    title: 'Enter your API Key',
    subtitle: 'Get a free key from dashboard.sarvam.ai\nWorks with Groq, Gemini, OpenAI too.',
    hint: null,
  },
  {
    id: 'google',
    title: 'Connect Google',
    subtitle: 'Needed for Gmail and Calendar.\nOpen this URL in your browser:',
    hint: null,
  },
  {
    id: 'done',
    title: "You're all set!",
    subtitle: 'PhoneAgent is ready.\nTry: "Set alarm for 7 AM" or\n"Kal subah 8 baje alarm lagao"',
    hint: null,
  },
];

const PROVIDERS = [
  { key: 'sarvam', label: 'Sarvam AI',  model: 'sarvam-30b',            baseUrl: 'https://api.sarvam.ai/v1' },
  { key: 'groq',   label: 'Groq',       model: 'llama-3.3-70b-versatile', baseUrl: 'https://api.groq.com/openai/v1' },
  { key: 'gemini', label: 'Gemini',     model: 'gemini-2.0-flash',        baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai' },
  { key: 'openai', label: 'OpenAI',     model: 'gpt-4o-mini',             baseUrl: 'https://api.openai.com/v1' },
];

export default function OnboardingScreen({ navigation }) {
  const [step,       setStep]       = useState(0);
  const [provider,   setProvider]   = useState('sarvam');
  const [apiKey,     setApiKey]     = useState('');
  const [backendUrl, setBackendUrl] = useState('http://10.0.2.2:8000');
  const [loading,    setLoading]    = useState(false);
  const [backendOk,  setBackendOk]  = useState(false);

  const current = STEPS[step];
  const isLast  = step === STEPS.length - 1;

  const handleTestBackend = async () => {
    setLoading(true);
    const health = await checkBackendHealth(backendUrl);
    setLoading(false);
    if (health.online) {
      setBackendOk(true);
      Alert.alert('Connected!', 'Backend is running.');
    } else {
      Alert.alert('Not found', 'Make sure uvicorn is running on your laptop.');
    }
  };

  const handleNext = async () => {
    if (current.id === 'apikey') {
      if (!apiKey.trim()) {
        Alert.alert('Required', 'Please enter your API key.');
        return;
      }
      const selected = PROVIDERS.find(p => p.key === provider);
      await saveProviderSettings({
        provider,
        apiKey,
        model:      selected.model,
        baseUrl:    selected.baseUrl,
        backendUrl,
      });
    }
    if (isLast) {
      navigation.replace('Chat');
    } else {
      setStep(s => s + 1);
    }
  };

  const openGoogleAuth = async () => {
    const selected = PROVIDERS.find(p => p.key === provider);
    await saveProviderSettings({
      provider,
      apiKey,
      model: selected.model,
      baseUrl: selected.baseUrl,
      backendUrl,
    });
    const url = await getGoogleLoginUrl();
    Linking.openURL(url);
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">

        {/* Step dots */}
        <View style={styles.dots}>
          {STEPS.map((_, i) => (
            <View
              key={i}
              style={[styles.dot, i === step && styles.dotActive]}
            />
          ))}
        </View>

        {/* Title */}
        <Text style={styles.title}>{current.title}</Text>
        <Text style={styles.subtitle}>{current.subtitle}</Text>

        {/* Code hint block */}
        {current.hint && (
          <View style={styles.codeBlock}>
            <Text style={styles.codeText}>{current.hint}</Text>
          </View>
        )}

        {/* STEP: backend */}
        {current.id === 'backend' && (
          <View style={styles.section}>
            <Text style={styles.label}>Backend URL</Text>
            <TextInput
              style={styles.input}
              value={backendUrl}
              onChangeText={setBackendUrl}
              placeholder="http://10.0.2.2:8000"
              placeholderTextColor="#555"
              autoCapitalize="none"
            />
            <Text style={styles.hint}>
              Android emulator: 10.0.2.2{'\n'}
              Real device: your laptop's WiFi IP
            </Text>
            <TouchableOpacity style={styles.outlineBtn} onPress={handleTestBackend}>
              {loading
                ? <ActivityIndicator color={ORANGE} />
                : <Text style={styles.outlineBtnText}>
                    {backendOk ? 'Connected!' : 'Test Connection'}
                  </Text>
              }
            </TouchableOpacity>
          </View>
        )}

        {/* STEP: apikey */}
        {current.id === 'apikey' && (
          <View style={styles.section}>
            {/* Provider selector */}
            <Text style={styles.label}>Choose Provider</Text>
            <View style={styles.providerRow}>
              {PROVIDERS.map(p => (
                <TouchableOpacity
                  key={p.key}
                  style={[styles.chip, provider === p.key && styles.chipActive]}
                  onPress={() => setProvider(p.key)}
                >
                  <Text style={[styles.chipText, provider === p.key && styles.chipTextActive]}>
                    {p.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* API Key input */}
            <Text style={styles.label}>API Key</Text>
            <TextInput
              style={styles.input}
              value={apiKey}
              onChangeText={setApiKey}
              placeholder="Paste your API key here..."
              placeholderTextColor="#555"
              secureTextEntry
              autoCapitalize="none"
            />
            <Text style={styles.hint}>
              Stored only on your device. Never sent to our servers.
            </Text>
          </View>
        )}

        {/* STEP: google */}
        {current.id === 'google' && (
          <View style={styles.section}>
            <View style={styles.codeBlock}>
              <Text style={styles.codeText}>{backendUrl}/auth/login</Text>
            </View>
            <TouchableOpacity style={styles.orangeBtn} onPress={openGoogleAuth}>
              <Text style={styles.orangeBtnText}>Open in Browser</Text>
            </TouchableOpacity>
            <Text style={styles.hint}>
              This connects Gmail and Google Calendar.{'\n'}
              You can skip this and add it later in Settings.
            </Text>
          </View>
        )}

      </ScrollView>

      {/* Bottom nav */}
      <View style={styles.bottom}>
        {step > 0 && (
          <TouchableOpacity onPress={() => setStep(s => s - 1)} style={styles.backBtn}>
            <Text style={styles.backBtnText}>Back</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity style={styles.nextBtn} onPress={handleNext}>
          <Text style={styles.nextBtnText}>
            {isLast ? 'Start Using PhoneAgent' : 'Next'}
          </Text>
        </TouchableOpacity>
      </View>

    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
 container: {
  flex: 1,
  backgroundColor: '#000',
  paddingTop: Platform.OS === 'android' ? StatusBar.currentHeight : 0,
},
  scroll:          { padding: 28, paddingBottom: 120 },
  dots:            { flexDirection: 'row', gap: 8, marginBottom: 40 },
  dot:             { width: 8, height: 8, borderRadius: 4, backgroundColor: '#333' },
  dotActive:       { backgroundColor: ORANGE, width: 24 },
  title:           { fontSize: 32, fontWeight: '900', color: '#fff', marginBottom: 12 },
  subtitle:        { fontSize: 16, color: '#888', lineHeight: 24, marginBottom: 24 },
  codeBlock:       {
    backgroundColor: '#111', borderRadius: 12, padding: 16,
    borderWidth: 1, borderColor: '#2a2a2a', marginBottom: 20,
  },
  codeText:        { color: ORANGE, fontSize: 14, fontFamily: 'monospace' },
  section:         { width: '100%' },
  label:           { fontSize: 14, fontWeight: '600', color: '#aaa', marginBottom: 8, marginTop: 16 },
  input:           {
    backgroundColor: '#111', borderRadius: 12, paddingHorizontal: 16,
    paddingVertical: 14, fontSize: 15, color: '#fff',
    borderWidth: 1, borderColor: '#2a2a2a',
  },
  hint:            { fontSize: 12, color: '#555', marginTop: 8, lineHeight: 18 },
  providerRow:     { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip:            {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20,
    backgroundColor: '#111', borderWidth: 1, borderColor: '#333',
  },
  chipActive:      { backgroundColor: ORANGE, borderColor: ORANGE },
  chipText:        { color: '#666', fontSize: 13, fontWeight: '600' },
  chipTextActive:  { color: '#000' },
  outlineBtn:      {
    borderWidth: 1, borderColor: ORANGE, borderRadius: 12,
    padding: 14, alignItems: 'center', marginTop: 16,
  },
  outlineBtnText:  { color: ORANGE, fontWeight: '700', fontSize: 15 },
  orangeBtn:       {
    backgroundColor: ORANGE, borderRadius: 12,
    padding: 14, alignItems: 'center', marginTop: 8,
  },
  orangeBtnText:   { color: '#000', fontWeight: '800', fontSize: 15 },
  bottom:          {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    flexDirection: 'row', gap: 10, padding: 20,
    backgroundColor: '#000', borderTopWidth: 1, borderTopColor: '#111',
  },
  backBtn:         {
    flex: 1, padding: 16, borderRadius: 14, alignItems: 'center',
    borderWidth: 1, borderColor: '#333',
  },
  backBtnText:     { color: '#666', fontWeight: '700', fontSize: 15 },
  nextBtn:         { flex: 2, backgroundColor: ORANGE, padding: 16, borderRadius: 14, alignItems: 'center' },
  nextBtnText:     { color: '#000', fontWeight: '800', fontSize: 15 },
});
