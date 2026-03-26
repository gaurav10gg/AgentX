import { NativeModules, Platform } from 'react-native';

const { AutomationBridge } = NativeModules;

const ensureAndroidModule = () => {
  if (Platform.OS !== 'android') {
    throw new Error('V2 automation is currently Android-only.');
  }
  if (!AutomationBridge) {
    throw new Error('AutomationBridge native module is not available. Build the Android app again.');
  }
  return AutomationBridge;
};

export const requestAccessibilityStatus = async () => {
  return ensureAndroidModule().requestAccessibilityStatus();
};

export const openAccessibilitySettings = async () => {
  return ensureAndroidModule().openAccessibilitySettings();
};

export const getForegroundApp = async () => {
  return ensureAndroidModule().getForegroundApp();
};

export const openApp = async (packageName) => {
  return ensureAndroidModule().openApp(packageName);
};

export const getCurrentUiTree = async () => {
  return ensureAndroidModule().getCurrentUiTree();
};

export const performAction = async (action, params = {}) => {
  return ensureAndroidModule().performAction(action, params);
};
