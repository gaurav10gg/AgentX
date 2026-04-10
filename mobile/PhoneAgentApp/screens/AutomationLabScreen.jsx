import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  cancelV2Task,
  getV2Apps,
  getV2Tasks,
  sendV2Message,
  sendV2Observation,
} from '../services/api';
import {
  getCurrentUiTree,
  openAccessibilitySettings,
  openApp,
  requestAccessibilityStatus,
} from '../services/automationBridge';
import { buildObservationPayload } from '../services/deviceState';
import { runV2AutomationLoop } from '../services/v2AutomationRuntime';

const ORANGE = '#FF6B35';

const QUICK_TASKS = [
  'Open Swiggy',
  'Search biryani on Swiggy',
  'Order biryani under 250 with rating above 4.5 using cash on delivery',
];

const createLogEntry = (kind, message) => ({
  id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
  kind,
  message,
});

export default function AutomationLabScreen({ navigation }) {
  const [prompt, setPrompt] = useState(QUICK_TASKS[0]);
  const [status, setStatus] = useState(null);
  const [apps, setApps] = useState([]);
  const [taskState, setTaskState] = useState(null);
  const [normalizedScreen, setNormalizedScreen] = useState(null);
  const [logs, setLogs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    bootstrap();
  }, []);

  const appSummary = useMemo(
    () => apps.map((app) => `${app.name} -> ${app.package}`).join('\n'),
    [apps]
  );

  const appendLog = (kind, message) => {
    setLogs((current) => [createLogEntry(kind, message), ...current].slice(0, 18));
  };

  const promptEnableAccessibility = () => {
    Alert.alert(
      'Accessibility Required',
      'Accessibility is off. Enable it to continue V2 automation.',
      [
        { text: 'Not now', style: 'cancel' },
        { text: 'Open Settings', onPress: handleOpenAccessibility },
      ]
    );
  };

  const ensureAccessibilityReady = async (sourceLabel = 'automation') => {
    const nextStatus = await requestAccessibilityStatus();
    setStatus(nextStatus);
    if (!nextStatus?.enabled) {
      appendLog('warn', `Accessibility is off. Enable it to continue ${sourceLabel}.`);
      promptEnableAccessibility();
      return null;
    }
    return nextStatus;
  };

  const bootstrap = async () => {
    setRefreshing(true);
    try {
      const [nextStatus, appList, tasks] = await Promise.all([
        requestAccessibilityStatus(),
        getV2Apps(),
        getV2Tasks(),
      ]);
      setStatus(nextStatus);
      const normalizedApps = Array.isArray(appList?.apps)
        ? appList.apps
        : Array.isArray(appList)
          ? appList
          : Object.values(appList || {});
      setApps(normalizedApps);
      const currentTask = tasks.tasks?.[0] || null;
      setTaskState(currentTask);
      setNormalizedScreen(currentTask?.latest_screen || null);
    } catch (error) {
      appendLog('error', error.message || 'Failed to load V2 automation state.');
    } finally {
      setRefreshing(false);
    }
  };

  const runTask = async () => {
    if (!prompt.trim() || busy) {
      return;
    }

    setBusy(true);
    try {
      const accessibility = await ensureAccessibilityReady('V2 task');
      if (!accessibility) {
        return;
      }
      appendLog('user', prompt.trim());
      const response = await sendV2Message(prompt.trim(), {
        accessibilityEnabled: accessibility.enabled,
        accessibilityConnected: accessibility.connected,
      });
      setTaskState(response.task_state || null);
      appendLog('assistant', response.reply);
      await continueAutomation(response, 8);
    } catch (error) {
      appendLog('error', error.message || 'Could not start V2 task.');
    } finally {
      setBusy(false);
    }
  };

  const captureNow = async () => {
    setBusy(true);
    try {
      const accessibility = await ensureAccessibilityReady('screen capture');
      if (!accessibility) {
        return;
      }
      const payload = await buildObservationPayload();
      const response = await sendV2Observation(payload);
      setTaskState(response.task_state || null);
      setNormalizedScreen(response.normalized_screen || null);
      appendLog('observe', response.reply || 'Sent current UI tree to backend.');
    } catch (error) {
      appendLog('error', error.message || 'Could not capture current screen.');
    } finally {
      setBusy(false);
    }
  };

  const stopAutomation = async () => {
    if (busy) {
      return;
    }
    setBusy(true);
    try {
      const response = await cancelV2Task('user_requested_stop');
      setTaskState(response?.task_state || null);
      appendLog('warn', 'Automation stopped by user.');
    } catch (error) {
      appendLog('error', error.message || 'Failed to stop automation.');
    } finally {
      setBusy(false);
    }
  };

  const continueAutomation = async (response, stepsRemaining) => {
    const accessibility = await ensureAccessibilityReady('automation loop');
    if (!accessibility) {
      return;
    }
    await runV2AutomationLoop({
      initialResponse: response,
      maxSteps: stepsRemaining,
      ensureReady: async (source) => ensureAccessibilityReady(source),
      onTaskState: (nextTaskState) => setTaskState(nextTaskState),
      onNormalizedScreen: (screen) => setNormalizedScreen(screen),
      onProgress: ({ level, message }) => appendLog(level, message),
    });
  };

  const handleOpenAccessibility = async () => {
    try {
      await openAccessibilitySettings();
    } catch (error) {
      Alert.alert('Accessibility', error.message || 'Could not open accessibility settings.');
    }
  };

  const refreshStatus = async () => {
    try {
      const nextStatus = await requestAccessibilityStatus();
      setStatus(nextStatus);
      appendLog('info', `Accessibility enabled=${nextStatus.enabled} connected=${nextStatus.connected}`);
    } catch (error) {
      appendLog('error', error.message || 'Could not refresh accessibility state.');
    }
  };

  const probeSnapshot = async () => {
    try {
      const snapshot = await getCurrentUiTree();
      if (!snapshot?.ui_tree) {
        appendLog('warn', 'No active UI tree yet. Open an app and try again.');
        return;
      }
      appendLog('observe', `Captured snapshot for ${snapshot.foreground_app || 'unknown app'}.`);
    } catch (error) {
      appendLog('error', error.message || 'Snapshot probe failed.');
    }
  };

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right', 'bottom']}>
      <StatusBar barStyle="light-content" backgroundColor="#000" />

      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.backBtn}>{'< Back'}</Text>
        </TouchableOpacity>
        <Text style={styles.heading}>Automation Lab</Text>
        <TouchableOpacity onPress={bootstrap} disabled={refreshing}>
          <Text style={styles.refreshBtn}>{refreshing ? '...' : 'Refresh'}</Text>
        </TouchableOpacity>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.hero}>
          <Text style={styles.heroTitle}>AgentX V2</Text>
          <Text style={styles.heroSubtitle}>
            Accessibility-first mobile automation for Swiggy-style tasks. This screen lets you inspect, drive, and debug the new V2 loop.
          </Text>
        </View>

        <View style={styles.statusCard}>
          <Text style={styles.cardTitle}>Device Readiness</Text>
          <Text style={styles.statusLine}>Accessibility enabled: {status?.enabled ? 'Yes' : 'No'}</Text>
          <Text style={styles.statusLine}>Service connected: {status?.connected ? 'Yes' : 'No'}</Text>
          <Text style={styles.statusLine}>Foreground app: {status?.foregroundApp || 'Unknown'}</Text>
          {!status?.enabled && (
            <Text style={styles.warnText}>
              Accessibility is required. Enable it before running V2 tasks.
            </Text>
          )}
          <View style={styles.row}>
            <TouchableOpacity style={styles.secondaryBtn} onPress={refreshStatus}>
              <Text style={styles.secondaryBtnText}>Check Status</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.primaryBtn} onPress={handleOpenAccessibility}>
              <Text style={styles.primaryBtnText}>Open Accessibility Settings</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Start a V2 Task</Text>
          <TextInput
            style={styles.input}
            value={prompt}
            onChangeText={setPrompt}
            placeholder="Order biryani under 250 with rating above 4.5"
            placeholderTextColor="#555"
            multiline
            autoCapitalize="sentences"
            editable={!busy}
          />
          <View style={styles.quickList}>
            {QUICK_TASKS.map((item) => (
              <TouchableOpacity key={item} style={styles.quickChip} onPress={() => setPrompt(item)} disabled={busy}>
                <Text style={styles.quickChipText}>{item}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <View style={styles.row}>
            <TouchableOpacity style={styles.primaryBtn} onPress={runTask} disabled={busy || status?.enabled === false}>
              {busy ? <ActivityIndicator color="#000" /> : <Text style={styles.primaryBtnText}>Run Task</Text>}
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryBtn} onPress={captureNow} disabled={busy}>
              <Text style={styles.secondaryBtnText}>Send Current Screen</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Manual Probes</Text>
          <View style={styles.row}>
            <TouchableOpacity style={styles.secondaryBtn} onPress={probeSnapshot}>
              <Text style={styles.secondaryBtnText}>Capture Snapshot</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.secondaryBtn}
              onPress={() => openApp('in.swiggy.android').then((ok) => appendLog(ok ? 'action' : 'error', ok ? 'Swiggy launch requested.' : 'Swiggy launch failed.'))}
            >
              <Text style={styles.secondaryBtnText}>Open Swiggy</Text>
            </TouchableOpacity>
          </View>
          {!!appSummary && <Text style={styles.monoBlock}>{appSummary}</Text>}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Current Task State</Text>
          <Text style={styles.stateLine}>Mode: {taskState?.mode || 'idle'}</Text>
          <Text style={styles.stateLine}>Status: {taskState?.status || 'idle'}</Text>
          <Text style={styles.stateLine}>Current package: {taskState?.current_package || 'n/a'}</Text>
          <Text style={styles.stateLine}>Pending action: {taskState?.pending_action?.action || 'none'}</Text>
          <View style={styles.row}>
            <TouchableOpacity
              style={styles.secondaryBtn}
              onPress={stopAutomation}
              disabled={busy || !taskState || !['active', 'awaiting_user'].includes(taskState?.status)}
            >
              <Text style={styles.secondaryBtnText}>Stop Automation</Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.replyBox}>{taskState?.reply || 'No active V2 task yet.'}</Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Normalized Screen</Text>
          <Text style={styles.stateLine}>Signature: {normalizedScreen?.screen_signature || 'n/a'}</Text>
          <Text style={styles.stateLine}>Anchors: {(normalizedScreen?.anchors || []).join(', ') || 'none'}</Text>
          <Text style={styles.monoBlock}>
            {normalizedScreen?.html ? normalizedScreen.html.slice(0, 2000) : 'No normalized screen captured yet.'}
          </Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Execution Trace</Text>
          {logs.length === 0 ? (
            <Text style={styles.emptyText}>No automation events yet.</Text>
          ) : (
            logs.map((entry) => (
              <View key={entry.id} style={styles.logRow}>
                <View
                  style={[
                    styles.logBadge,
                    entry.kind === 'error' ? styles.badgeError : entry.kind === 'warn' ? styles.badgeWarn : styles.badgeInfo,
                  ]}
                >
                  <Text style={styles.logBadgeText}>{entry.kind}</Text>
                </View>
                <Text style={styles.logText}>{entry.message}</Text>
              </View>
            ))
          )}
        </View>
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
  backBtn: { color: ORANGE, fontSize: 15, fontWeight: '700', width: 70 },
  heading: { fontSize: 20, fontWeight: '900', color: '#fff' },
  refreshBtn: { width: 70, textAlign: 'right', color: '#9ca3af', fontWeight: '700' },
  scroll: { flex: 1, backgroundColor: '#000' },
  scrollContent: { paddingHorizontal: 18, paddingBottom: 48 },
  hero: { marginTop: 16, marginBottom: 14 },
  heroTitle: { color: '#fff', fontSize: 28, fontWeight: '900', marginBottom: 6 },
  heroSubtitle: { color: '#8d8d8d', fontSize: 13, lineHeight: 20 },
  card: {
    backgroundColor: '#111',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#232323',
    marginBottom: 14,
    gap: 12,
  },
  statusCard: {
    backgroundColor: '#130f0c',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#3c251b',
    marginBottom: 14,
    gap: 10,
  },
  cardTitle: { color: '#fff', fontWeight: '800', fontSize: 16 },
  statusLine: { color: '#d6d3d1', fontSize: 13 },
  warnText: { color: '#fca5a5', fontSize: 13, fontWeight: '700' },
  stateLine: { color: '#b6b6b6', fontSize: 13 },
  replyBox: {
    color: '#f4f4f5',
    fontSize: 14,
    lineHeight: 20,
    backgroundColor: '#171717',
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: '#292929',
  },
  row: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
  primaryBtn: {
    backgroundColor: ORANGE,
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 46,
    flexGrow: 1,
  },
  primaryBtnText: { color: '#000', fontWeight: '900', fontSize: 14 },
  secondaryBtn: {
    backgroundColor: '#181818',
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: '#313131',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 46,
    flexGrow: 1,
  },
  secondaryBtnText: { color: '#d4d4d8', fontWeight: '700', fontSize: 13 },
  input: {
    backgroundColor: '#151515',
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
    minHeight: 88,
    color: '#fff',
    borderWidth: 1,
    borderColor: '#2d2d2d',
    textAlignVertical: 'top',
    fontSize: 15,
  },
  quickList: { gap: 8 },
  quickChip: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#2d2d2d',
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: '#141414',
  },
  quickChipText: { color: '#b8b8b8', fontSize: 13 },
  monoBlock: {
    backgroundColor: '#0b0b0b',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#222',
    padding: 12,
    color: '#c7c7c7',
    fontSize: 12,
    lineHeight: 18,
    fontFamily: 'monospace',
  },
  emptyText: { color: '#7a7a7a', fontSize: 13 },
  logRow: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'flex-start',
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: '#1d1d1d',
  },
  logBadge: {
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 4,
    minWidth: 54,
    alignItems: 'center',
  },
  badgeInfo: { backgroundColor: '#1d283a' },
  badgeWarn: { backgroundColor: '#3a270f' },
  badgeError: { backgroundColor: '#3b1313' },
  logBadgeText: { color: '#f4f4f5', fontSize: 11, fontWeight: '800', textTransform: 'uppercase' },
  logText: { flex: 1, color: '#d4d4d8', fontSize: 13, lineHeight: 18 },
});
