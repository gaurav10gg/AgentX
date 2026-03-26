// services/storage.js
import AsyncStorage from '@react-native-async-storage/async-storage';

export const saveProviderSettings = async ({ provider, apiKey, model, baseUrl, backendUrl }) => {
  await AsyncStorage.setItem('pa_provider',    provider    || 'sarvam');
  await AsyncStorage.setItem('pa_api_key',     apiKey      || '');
  await AsyncStorage.setItem('pa_model',       model       || 'sarvam-30b');
  await AsyncStorage.setItem('pa_base_url',    baseUrl     || 'https://api.sarvam.ai/v1');
  await AsyncStorage.setItem('pa_backend_url', backendUrl  || 'http://10.0.2.2:8000');
};

export const getProviderSettings = async () => {
  const provider   = await AsyncStorage.getItem('pa_provider');
  const apiKey     = await AsyncStorage.getItem('pa_api_key');
  const model      = await AsyncStorage.getItem('pa_model');
  const baseUrl    = await AsyncStorage.getItem('pa_base_url');
  const backendUrl = await AsyncStorage.getItem('pa_backend_url');
  return {
    provider:   provider   || 'sarvam',
    apiKey:     apiKey     || '',
    model:      model      || 'sarvam-30b',
    baseUrl:    baseUrl    || 'https://api.sarvam.ai/v1',
    backendUrl: backendUrl || 'http://10.0.2.2:8000',
  };
};

export const isConfigured = async () => {
  const apiKey = await AsyncStorage.getItem('pa_api_key');
  return apiKey !== null && apiKey.length > 0;
};

export const getOrCreateSessionId = async () => {
  let sessionId = await AsyncStorage.getItem('pa_session_id');
  if (!sessionId) {
    sessionId = `session_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    await AsyncStorage.setItem('pa_session_id', sessionId);
  }
  return sessionId;
};

export const resetSession = async () => {
  const sessionId = `session_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  await AsyncStorage.setItem('pa_session_id', sessionId);
  return sessionId;
};

export const saveChatHistory = async (messages) => {
  await AsyncStorage.setItem('pa_chat_history', JSON.stringify(messages));
};

export const loadChatHistory = async () => {
  const raw = await AsyncStorage.getItem('pa_chat_history');
  return raw ? JSON.parse(raw) : [];
};

export const clearChatHistory = async () => {
  await AsyncStorage.removeItem('pa_chat_history');
};

export const getOrCreateUserId = async () => {
  let userId = await AsyncStorage.getItem('pa_user_id');
  if (!userId) {
    userId = `user_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    await AsyncStorage.setItem('pa_user_id', userId);
  }
  return userId;
};

export const getOrCreateDeviceId = async () => {
  let deviceId = await AsyncStorage.getItem('pa_device_id');
  if (!deviceId) {
    deviceId = `device_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    await AsyncStorage.setItem('pa_device_id', deviceId);
  }
  return deviceId;
};
