// mobile/services/api.js
import axios from 'axios';
import { getProviderSettings, getOrCreateDeviceId, getOrCreateSessionId, getOrCreateUserId } from './storage';

const getClient = async (backendUrlOverride) => {
  const { backendUrl } = await getProviderSettings();
  return axios.create({
    baseURL: backendUrlOverride || backendUrl || 'http://10.0.2.2:8000',
    timeout: 30000,
    headers: { 'Content-Type': 'application/json' },
  });
};

export const sendMessage = async (message, options = {}) => {
  const client = await getClient();
  const { provider, apiKey, model, baseUrl } = await getProviderSettings();
  const sessionId = await getOrCreateSessionId();
  const userId = await getOrCreateUserId();
  const deviceId = await getOrCreateDeviceId();

  const response = await client.post('/chat', {
    message,
    session_id: sessionId,
    user_id: userId,
    device_id: options.deviceId || deviceId,
    accessibility_enabled: options.accessibilityEnabled ?? undefined,
    accessibility_connected: options.accessibilityConnected ?? undefined,
    provider,
    api_key:  apiKey,
    model:    model    || undefined,
    base_url: baseUrl  || undefined,
  });
  return response.data;
  // { reply, actions_taken, alarm_data, requires_confirmation }
};

export const clearHistory = async () => {
  const client = await getClient();
  const sessionId = await getOrCreateSessionId();
  await client.delete(`/chat/history/${sessionId}`);
};

export const getGoogleAuthStatus = async () => {
  const userId = await getOrCreateUserId();
  const client = await getClient();
  const res = await client.get('/auth/status', { params: { user_id: userId } });
  return res.data;
};

export const getGoogleLoginUrl = async () => {
  const { backendUrl } = await getProviderSettings();
  const userId = await getOrCreateUserId();
  return `${backendUrl}/auth/login?user_id=${encodeURIComponent(userId)}`;
};

export const getProviderPresets = async () => {
  const client = await getClient();
  const res = await client.get('/providers');
  return res.data;
};

export const checkBackendHealth = async (backendUrlOverride) => {
  try {
    const client = await getClient(backendUrlOverride);
    const userId = await getOrCreateUserId();
    const res = await client.get('/', { params: { user_id: userId } });
    return { online: true, ...res.data };
  } catch {
    return { online: false };
  }
};

export const logoutGoogle = async (backendUrlOverride) => {
  const userId = await getOrCreateUserId();
  const client = await getClient(backendUrlOverride);
  const res = await client.delete('/auth/logout', { params: { user_id: userId } });
  return res.data;
};

export const sendV2Message = async (message, options = {}) => {
  const client = await getClient();
  const { provider, apiKey, model, baseUrl } = await getProviderSettings();
  const sessionId = await getOrCreateSessionId();
  const userId = await getOrCreateUserId();
  const deviceId = await getOrCreateDeviceId();

  const response = await client.post('/v2/chat', {
    message,
    session_id: sessionId,
    user_id: userId,
    device_id: deviceId,
    accessibility_enabled: options.accessibilityEnabled ?? undefined,
    accessibility_connected: options.accessibilityConnected ?? undefined,
    provider,
    api_key: apiKey,
    model: model || undefined,
    base_url: baseUrl || undefined,
  });
  return response.data;
};

export const sendV2Observation = async (observation) => {
  const client = await getClient();
  const { provider, apiKey, model, baseUrl } = await getProviderSettings();

  const response = await client.post('/v2/device/observe', observation, {
    params: {
      provider,
      api_key: apiKey || undefined,
      model: model || undefined,
      base_url: baseUrl || undefined,
    },
  });
  return response.data;
};

export const sendV2ActionResult = async ({ action, success = true, result = null, observation = null }) => {
  const client = await getClient();
  const { provider, apiKey, model, baseUrl } = await getProviderSettings();
  const sessionId = await getOrCreateSessionId();
  const userId = await getOrCreateUserId();
  const deviceId = await getOrCreateDeviceId();

  const response = await client.post('/v2/device/action-result', {
    session_id: sessionId,
    user_id: userId,
    device_id: deviceId,
    accessibility_enabled: observation?.accessibility_enabled ?? undefined,
    accessibility_connected: observation?.accessibility_connected ?? undefined,
    action,
    success,
    result,
    observation,
  }, {
    params: {
      provider,
      api_key: apiKey || undefined,
      model: model || undefined,
      base_url: baseUrl || undefined,
    },
  });
  return response.data;
};

export const getV2Apps = async () => {
  const client = await getClient();
  const response = await client.get('/v2/apps');
  return Array.isArray(response.data) ? response.data : Object.values(response.data || {});
};

export const getV2Tasks = async () => {
  const client = await getClient();
  const sessionId = await getOrCreateSessionId();
  const response = await client.get(`/v2/tasks/${sessionId}`);
  return response.data;
};

export const cancelV2Task = async (reason = 'user_cancelled') => {
  const client = await getClient();
  const sessionId = await getOrCreateSessionId();
  const response = await client.post(`/v2/tasks/${sessionId}/cancel`, null, {
    params: { reason },
  });
  return response.data;
};
