import { openApp, performAction } from './automationBridge';
import { sendV2ActionResult, sendV2Observation } from './api';
import { buildObservationPayload } from './deviceState';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const actionLabel = (action) =>
  `${action.action}${action.element_id ? ` -> ${action.element_id}` : ''}`;

const push = (onProgress, level, message) => {
  if (onProgress) onProgress({ level, message });
};

async function executeStep(action, onProgress, onTaskState, onNormalizedScreen) {
  if (action.action === 'open_app') {
    const success = await openApp(action.package_name || '');
    push(
      onProgress,
      success ? 'action' : 'error',
      success ? `Opened ${action.package_name}` : `Failed to open ${action.package_name}`
    );
    await sleep(1200);
    const payload = await buildObservationPayload();
    const response = await sendV2Observation(payload);
    if (onTaskState) onTaskState(response.task_state || null);
    if (onNormalizedScreen) onNormalizedScreen(response.normalized_screen || null);
    return response;
  }

  if (action.action === 'request_observation') {
    const payload = await buildObservationPayload();
    const response = await sendV2Observation(payload);
    if (onTaskState) onTaskState(response.task_state || null);
    if (onNormalizedScreen) onNormalizedScreen(response.normalized_screen || null);
    push(onProgress, 'observe', response.reply || 'Sent a fresh observation.');
    return response;
  }

  const params = {
    elementId: action.element_id || null,
    text: action.input_text || '',
    direction: action.direction || 'down',
    timeoutMs: action.timeout_ms || 1200,
  };
  const result = await performAction(action.action, params);
  await sleep(action.action === 'wait_for' ? (action.timeout_ms || 1200) : 800);

  const observation = await buildObservationPayload();
  const response = await sendV2ActionResult({
    action,
    success: Boolean(result?.success),
    result: result?.success
      ? `${action.action} executed on device.`
      : `${action.action} failed on device.`,
    observation,
  });

  if (onTaskState) onTaskState(response.task_state || null);
  if (onNormalizedScreen) onNormalizedScreen(response.normalized_screen || null);
  push(
    onProgress,
    result?.success ? 'action' : 'error',
    result?.success ? `Executed ${action.action}` : `Failed ${action.action}`
  );
  return response;
}

export async function runV2AutomationLoop({
  initialResponse,
  maxSteps = 8,
  ensureReady,
  onProgress,
  onTaskState,
  onNormalizedScreen,
}) {
  let current = initialResponse;
  let remaining = maxSteps;

  while (current?.next_action && remaining > 0) {
    const action = current.next_action;
    if (onTaskState) onTaskState(current.task_state || null);
    push(onProgress, 'plan', `Next: ${actionLabel(action)}`);

    if (action.action === 'complete' || action.action === 'ask_user') {
      break;
    }

    if (current?.task_state?.safety_reason_code === 'accessibility_disabled') {
      push(onProgress, 'warn', 'Automation paused because accessibility is disabled.');
      break;
    }

    try {
      if (ensureReady) {
        const ready = await ensureReady(`action ${action.action}`);
        if (!ready) {
          push(onProgress, 'warn', 'Automation paused until accessibility is enabled.');
          break;
        }
      }

      current = await executeStep(action, onProgress, onTaskState, onNormalizedScreen);
      remaining -= 1;
    } catch (error) {
      push(onProgress, 'error', error?.message || `Action ${action.action} failed unexpectedly.`);
      break;
    }
  }

  if (remaining === 0) {
    push(onProgress, 'warn', `Stopped after ${maxSteps} steps to avoid runaway automation.`);
  }

  return current;
}

