import { getCurrentUiTree, requestAccessibilityStatus } from './automationBridge';
import { getOrCreateDeviceId, getOrCreateSessionId, getOrCreateUserId } from './storage';

export const buildObservationPayload = async (snapshotOverride = null) => {
  const snapshot = snapshotOverride || await getCurrentUiTree();
  const accessibility = await requestAccessibilityStatus();
  if (!snapshot) {
    throw new Error('No accessibility snapshot is available yet.');
  }

  const sessionId = await getOrCreateSessionId();
  const userId = await getOrCreateUserId();
  const deviceId = await getOrCreateDeviceId();

  return {
    session_id: sessionId,
    user_id: userId,
    device_id: deviceId,
    foreground_app: snapshot.foreground_app || null,
    screen_title: snapshot.screen_title || null,
    timestamp: new Date().toISOString(),
    accessibility_enabled: accessibility?.enabled ?? null,
    accessibility_connected: accessibility?.connected ?? null,
    ui_tree: snapshot.ui_tree || null,
    metadata: {
      source: 'android_accessibility',
      accessibility_enabled: accessibility?.enabled ?? null,
      accessibility_connected: accessibility?.connected ?? null,
    },
  };
};
