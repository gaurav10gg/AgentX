import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export const requestAlarmPermissions = async () => {
  const { status } = await Notifications.requestPermissionsAsync();
  return status === 'granted';
};

export const setupNotificationChannel = async () => {
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('alarms', {
      name: 'Alarms',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 500, 200, 500],
      lightColor: '#FF6B35',
      sound: 'default',
      enableVibrate: true,
      showBadge: true,
    });
  }
};

export const setAlarm = async (hour, minute, label = 'PhoneAgent Alarm') => {
  const granted = await requestAlarmPermissions();
  if (!granted) {
    throw new Error('Notification permissions not granted');
  }

  const now = new Date();
  const alarm = new Date();
  alarm.setHours(hour, minute, 0, 0);

  if (alarm <= now) {
    alarm.setDate(alarm.getDate() + 1);
  }

  const secondsUntilAlarm = Math.floor((alarm.getTime() - now.getTime()) / 1000);

  await cancelAlarmByLabel(label);

  const id = await Notifications.scheduleNotificationAsync({
    content: {
      title: 'Alarm: ' + label,
      body: `Alarm for ${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`,
      sound: true,
      priority: Notifications.AndroidNotificationPriority.MAX,
      vibrate: [0, 500, 200, 500],
    },
    trigger: {
      seconds: secondsUntilAlarm,
      channelId: 'alarms',
    },
  });

  return {
    id,
    hour,
    minute,
    label,
    scheduledFor: alarm.toISOString(),
  };
};

export const cancelAlarmByLabel = async (label) => {
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  for (const notification of scheduled) {
    if (notification.content.title?.includes(label)) {
      await Notifications.cancelScheduledNotificationAsync(notification.identifier);
    }
  }
};

export const cancelAllAlarms = async () => {
  await Notifications.cancelAllScheduledNotificationsAsync();
};

export const getScheduledAlarms = async () => {
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  return scheduled.map((notification) => ({
    id: notification.identifier,
    title: notification.content.title,
    body: notification.content.body,
  }));
};
