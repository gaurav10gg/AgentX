import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Linking, ScrollView, StatusBar, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { checkBackendHealth, getGoogleAuthStatus, getGoogleLoginUrl, logoutGoogle } from '../services/api';
import { getProviderSettings, saveProviderSettings } from '../services/storage';

const ORANGE = '#FF6B35';

const PROVIDERS = [
  { key: 'sarvam', label: 'Sarvam AI', baseUrl: 'https://api.sarvam.ai/v1', model: 'sarvam-30b' },
  { key: 'groq', label: 'Groq', baseUrl: 'https://api.groq.com/openai/v1', model: 'llama-3.3-70b-versatile' },
  { key: 'gemini', label: 'Gemini', baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai', model: 'gemini-2.0-flash' },
  { key: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { key: 'custom', label: 'Custom', baseUrl: '', model: '' },
];

export default function SettingsScreen({ navigation }) {
  const [provider, setProvider] = useState('sarvam');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('sarvam-30b');
  const [baseUrl, setBaseUrl] = useState('https://api.sarvam.ai/v1');
  const [backendUrl, setBackendUrl] = useState('http://10.0.2.2:8000');
  const [saving, setSaving] = useState(false);
  const [backendOk, setBackendOk] = useState(null);
  const [googleOk, setGoogleOk] = useState(false);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  useEffect(() => {
    const unsubscribe = navigation.addListener('focus', () => {
      checkStatus(backendUrl);
    });
    return unsubscribe;
  }, [navigation, backendUrl]);

  const loadSettings = async () => {
    try {
      const stored = await getProviderSettings();
      setProvider(stored.provider);
      setApiKey(stored.apiKey);
      setModel(stored.model);
      setBaseUrl(stored.baseUrl);
      setBackendUrl(stored.backendUrl);
      await checkStatus(stored.backendUrl);
    } catch {
      Alert.alert('Settings Error', 'Could not load saved settings.');
    }
  };

  const persistSettings = async (overrides = {}) => {
    await saveProviderSettings({
      provider,
      apiKey,
      model,
      baseUrl,
      backendUrl,
      ...overrides,
    });
  };

  const isValidUrl = (value) => {
    try {
      const parsed = new URL(value);
      return Boolean(parsed.protocol && parsed.host);
    } catch {
      return false;
    }
  };

  const checkStatus = async (backendUrlOverride = backendUrl) => {
    const targetUrl = backendUrlOverride?.trim();
    const health = await checkBackendHealth(targetUrl);
    setBackendOk(health.online);
    if (!health.online) {
      setGoogleOk(false);
      return;
    }
    const google = await getGoogleAuthStatus();
    setGoogleOk(google.connected);
  };

  const selectProvider = (nextProvider) => {
    setProvider(nextProvider.key);
    if (nextProvider.key !== 'custom') {
      setBaseUrl(nextProvider.baseUrl);
      setModel(nextProvider.model);
    }
  };

  const handleSave = async () => {
    if (!apiKey.trim()) {
      Alert.alert('Missing API Key', 'Please enter your API key.');
      return;
    }
    if (!isValidUrl(backendUrl.trim())) {
      Alert.alert('Invalid Backend URL', 'Please enter a full URL like http://10.0.2.2:8000');
      return;
    }
    if (provider === 'custom' && !isValidUrl(baseUrl.trim())) {
      Alert.alert('Invalid Base URL', 'Please enter a full URL like https://api.example.com/v1');
      return;
    }

    setSaving(true);
    try {
      const cleanedBackendUrl = backendUrl.trim();
      const cleanedBaseUrl = baseUrl.trim();

      setBackendUrl(cleanedBackendUrl);
      if (provider === 'custom') {
        setBaseUrl(cleanedBaseUrl);
      }

      await persistSettings({
        backendUrl: cleanedBackendUrl,
        ...(provider === 'custom' ? { baseUrl: cleanedBaseUrl } : {}),
      });
      await checkStatus(cleanedBackendUrl);
      Alert.alert('Saved', 'Settings updated successfully.');
    } catch {
      Alert.alert('Save Failed', 'Could not save settings. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleConnectGoogle = async () => {
    if (!backendOk) {
      Alert.alert('Backend Offline', 'Start backend first, then try connecting Google.');
      return;
    }

    setConnecting(true);
    try {
      await persistSettings();
      const url = await getGoogleLoginUrl();
      await Linking.openURL(url);
      setTimeout(() => {
        checkStatus(backendUrl.trim());
        setConnecting(false);
      }, 4000);
    } catch {
      setConnecting(false);
      Alert.alert('Error', 'Failed to open browser for Google login.');
    }
  };

  const handleDisconnectGoogle = async () => {
    Alert.alert('Disconnect Google', 'Remove Gmail, Calendar and Contacts access?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Disconnect',
        style: 'destructive',
        onPress: async () => {
          try {
            await logoutGoogle(backendUrl);
            setGoogleOk(false);
          } catch {
            Alert.alert('Error', 'Failed to disconnect Google.');
          }
        },
      },
    ]);
  };

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right', 'bottom']}>
      <StatusBar barStyle="light-content" backgroundColor="#000" />

      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.backBtn}>{'< Back'}</Text>
        </TouchableOpacity>
        <Text style={styles.heading}>Settings</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.hero}>
          <Text style={styles.heroTitle}>Control Panel</Text>
          <Text style={styles.heroSubtitle}>Tune backend, model, and Google access in one place.</Text>
        </View>

        <View style={styles.statusCard}>
          <View style={styles.statusRow}>
            <View style={[styles.dot, { backgroundColor: backendOk ? '#22c55e' : '#ef4444' }]} />
            <Text style={styles.statusText}>Backend {backendOk ? 'Online' : 'Offline'}</Text>
            <TouchableOpacity onPress={() => checkStatus(backendUrl)} style={styles.refreshSmall}>
              <Text style={styles.refreshSmallText}>Refresh</Text>
            </TouchableOpacity>
          </View>
          <View style={styles.statusRow}>
            <View style={[styles.dot, { backgroundColor: googleOk ? '#22c55e' : '#f59e0b' }]} />
            <Text style={styles.statusText}>Google {googleOk ? 'Connected' : 'Not Connected'}</Text>
          </View>
        </View>

        <Text style={styles.sectionTitle}>Google Account</Text>
        <View style={styles.card}>
          {googleOk ? (
            <>
              <Text style={styles.googleConnectedText}>Connected for Gmail, Calendar, and Contacts.</Text>
              <TouchableOpacity style={styles.disconnectBtn} onPress={handleDisconnectGoogle}>
                <Text style={styles.disconnectBtnText}>Disconnect Google</Text>
              </TouchableOpacity>
            </>
          ) : (
            <>
              <Text style={styles.infoText}>Connect Google so the assistant can send email and read your schedule.</Text>
              <TouchableOpacity style={styles.googleBtn} onPress={handleConnectGoogle} disabled={connecting}>
                {connecting ? <ActivityIndicator color="#000" /> : <Text style={styles.googleBtnText}>Connect Gmail + Calendar</Text>}
              </TouchableOpacity>
              {!backendOk && <Text style={styles.warningText}>Backend is offline. Start it first.</Text>}
            </>
          )}
        </View>

        <Text style={styles.sectionTitle}>Automation</Text>
        <View style={styles.card}>
          <Text style={styles.infoText}>
            V2 runs mobile automation through Android accessibility. Use the Automation Lab to test app launch,
            UI capture, and the new observe-think-act loop.
          </Text>
          <TouchableOpacity style={styles.googleBtn} onPress={() => navigation.navigate('AutomationLab')}>
            <Text style={styles.googleBtnText}>Open Automation Lab</Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.sectionTitle}>LLM Provider</Text>
        <View style={styles.providerRow}>
          {PROVIDERS.map((item) => (
            <TouchableOpacity
              key={item.key}
              style={[styles.providerBtn, provider === item.key && styles.providerBtnActive]}
              onPress={() => selectProvider(item)}
            >
              <Text style={[styles.providerText, provider === item.key && styles.providerTextActive]}>
                {item.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.label}>API Key</Text>
        <TextInput
          style={styles.input}
          value={apiKey}
          onChangeText={setApiKey}
          placeholder="Enter your provider API key"
          placeholderTextColor="#555"
          secureTextEntry
          autoCapitalize="none"
          autoCorrect={false}
        />
        <Text style={styles.hint}>Stored locally on your device.</Text>

        <Text style={styles.label}>Model</Text>
        <TextInput
          style={styles.input}
          value={model}
          onChangeText={setModel}
          placeholder="e.g. sarvam-30b"
          placeholderTextColor="#555"
          autoCapitalize="none"
          autoCorrect={false}
        />

        {provider === 'custom' && (
          <>
            <Text style={styles.label}>Base URL</Text>
            <TextInput
              style={styles.input}
              value={baseUrl}
              onChangeText={setBaseUrl}
              placeholder="https://your-api.com/v1"
              placeholderTextColor="#555"
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
            />
          </>
        )}

        <Text style={styles.label}>Backend URL</Text>
        <TextInput
          style={styles.input}
          value={backendUrl}
          onChangeText={setBackendUrl}
          placeholder="http://10.0.2.2:8000"
          placeholderTextColor="#555"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />
        <Text style={styles.hint}>Emulator: 10.0.2.2 | Real phone: your laptop Wi-Fi IP.</Text>

        <TouchableOpacity style={styles.saveBtn} onPress={handleSave} disabled={saving}>
          {saving ? <ActivityIndicator color="#000" /> : <Text style={styles.saveBtnText}>Save Settings</Text>}
        </TouchableOpacity>

        <View style={styles.bottomSpacer} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: '#000' },
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
  backBtn: { color: ORANGE, fontSize: 15, fontWeight: '700', width: 64 },
  heading: { fontSize: 20, fontWeight: '900', color: '#fff', letterSpacing: 0.2 },
  headerSpacer: { width: 64 },
  scroll: { flex: 1, backgroundColor: '#000' },
  scrollContent: { paddingHorizontal: 18, paddingBottom: 60 },
  hero: { marginTop: 14, marginBottom: 14 },
  heroTitle: { color: '#fff', fontSize: 26, fontWeight: '900', marginBottom: 4 },
  heroSubtitle: { color: '#8e8e8e', fontSize: 13, lineHeight: 19 },
  statusCard: {
    backgroundColor: '#101010',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: '#212121',
    marginBottom: 18,
    gap: 10,
  },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  statusText: { fontSize: 13, color: '#a3a3a3', flex: 1, fontWeight: '600' },
  refreshSmall: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#343434',
    backgroundColor: '#171717',
  },
  refreshSmallText: { color: '#8d8d8d', fontSize: 12, fontWeight: '700' },
  sectionTitle: { fontSize: 16, fontWeight: '800', color: '#f6f6f6', marginBottom: 10, marginTop: 8 },
  card: {
    backgroundColor: '#111',
    borderRadius: 14,
    padding: 15,
    borderWidth: 1,
    borderColor: '#222',
    marginBottom: 18,
    gap: 10,
  },
  googleConnectedText: { fontSize: 14, color: '#86efac', fontWeight: '700' },
  infoText: { fontSize: 13, color: '#9b9b9b', lineHeight: 20 },
  googleBtn: { backgroundColor: ORANGE, borderRadius: 12, padding: 13, alignItems: 'center' },
  googleBtnText: { color: '#000', fontWeight: '900', fontSize: 15, letterSpacing: 0.2 },
  disconnectBtn: { borderWidth: 1, borderColor: '#ef4444', borderRadius: 12, padding: 12, alignItems: 'center' },
  disconnectBtnText: { color: '#ef4444', fontWeight: '700' },
  warningText: { fontSize: 12, color: '#f59e0b', textAlign: 'center' },
  label: { fontSize: 13, fontWeight: '700', color: '#b8b8b8', marginTop: 12, marginBottom: 6, letterSpacing: 0.3 },
  input: {
    backgroundColor: '#151515',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: '#fff',
    borderWidth: 1,
    borderColor: '#303030',
  },
  hint: { fontSize: 12, color: '#666', marginTop: 6, lineHeight: 16 },
  providerRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 2 },
  providerBtn: {
    paddingHorizontal: 13,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#151515',
    borderWidth: 1,
    borderColor: '#323232',
  },
  providerBtnActive: { backgroundColor: ORANGE, borderColor: ORANGE },
  providerText: { fontSize: 13, color: '#959595', fontWeight: '700' },
  providerTextActive: { color: '#000' },
  saveBtn: {
    backgroundColor: ORANGE,
    borderRadius: 14,
    padding: 16,
    alignItems: 'center',
    marginTop: 22,
  },
  saveBtnText: { color: '#000', fontSize: 16, fontWeight: '900', letterSpacing: 0.3 },
  bottomSpacer: { height: 80 },
});
