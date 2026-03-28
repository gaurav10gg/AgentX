# PhoneAgentApp

Expo-based Android client for PhoneX.

## Important: Native Automation Changes Require Rebuild

If you change anything under `android/` (Accessibility service, bridge module, action executor, manifest, or native permissions), **`expo start` is not enough**.
You must rebuild and reinstall the app:

```bash
npx expo run:android --device
```

Use this as the default workflow for V2 automation contributors.

## What lives here

- `App.js` bootstraps navigation
- `screens/` contains onboarding, chat, history, and settings
- `components/` contains reusable chat UI pieces
- `services/` contains backend API, local storage, and alarm helpers
- `assets/` contains app icons and images

## Run locally

```bash
npm install
npx expo start
```

Before using the app:

1. Start the backend from the repo root with `uvicorn server:app --reload`
2. In the app, set the backend URL to `10.0.2.2:8000` for the Android emulator or your laptop IP for a real device
3. Add your provider API key in Settings
4. Connect Google from the app when you want Gmail, Calendar, or Contacts access
