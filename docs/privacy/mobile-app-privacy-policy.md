# Privacy Policy

**Effective date:** July 22, 2026

Endurain (the "App") is the official mobile companion for Endurain, a self-hosted fitness tracking service. This Privacy Policy explains how the App handles information when you use it.

## Summary

The App is designed to work with an Endurain server selected by you. The App does not include advertising SDKs or behavioral analytics. Local diagnostic reports are never uploaded automatically. If you separately opt in to remote crash reporting, sanitized error reports are sent only to Endurain's own managed diagnostics endpoint, never to a third party, as described below.

Your selected Endurain server operator is responsible for its own server-side data handling. Review that operator's privacy policy before creating an account or connecting the App to its server.

## Information the App Processes

Depending on the features you use, the App processes the following information:

- **Account and connection information:** your Endurain server address, authentication session tokens, and account information returned by your selected Endurain server.
- **Location information:** precise or approximate device location while using the map or recording an activity. During a recording, location may be collected in the background so the route can continue to be recorded when the App is not on screen.
- **Activity information:** activity type, timestamps, elapsed time, distance, speed, route points, and GPX files created by the App.
- **Health information:** if you enable health synchronization, workout, exercise route, heart-rate, distance, calorie, and step information that you authorize the App to read through Apple HealthKit or Android Health Connect.
- **App diagnostics:** privacy-filtered error and lifecycle information stored locally to help you investigate a problem. Diagnostics intentionally exclude raw GPS coordinates and sanitize token-like values, paths, and coordinate-looking strings.
- **Optional remote crash reports:** if you enable remote crash reporting in Settings, sanitized exception details (with GPS coordinates, tokens, and file paths redacted) are sent to Endurain's managed diagnostics endpoint (diagnostics.endurain.com) using the Sentry protocol. This is off by default, independent of local diagnostics, and does not include breadcrumbs or personally-identifying information, though basic non-identifying metadata (app version, OS name/version) is included per the Sentry protocol.
- **Preferences:** language, display, map, and feature settings that you choose in the App.
- **External sensor information:** if you pair a Bluetooth Low Energy heart-rate, power, or cadence sensor, the App reads live physiological/performance readings from it and stamps them onto your recorded GPX track points. Paired-sensor identifiers are stored locally so the App can reconnect automatically.

## How Information Is Used

The App uses this information to:

- authenticate you with your selected Endurain server;
- display maps and your current position;
- record, save, export, share, and optionally upload activities;
- import health and workout data when you explicitly enable and authorize health synchronization;
- retain activity data for offline use and retry an upload you requested;
- diagnose problems locally on your device.

We do not use information processed by the App for advertising, sell it, or use it to determine creditworthiness, insurance eligibility, employment decisions, or any other unrelated profiling purpose.

## Where Information Is Stored and Sent

### On your device

The App stores authentication material in the operating system's secure storage. It stores activity metadata in a local database and GPX files in the App's private storage. Health-derived activity data is stored in dedicated local no-backup storage. Preferences and local diagnostics are also stored in the App's private storage.

### Your selected Endurain server

When you sign in or choose to upload an activity, the App sends the necessary account and activity information to the Endurain server you selected. The server operator controls that server, its location, retention period, backups, access controls, and any onward sharing. This policy does not replace the server operator's privacy policy.

### Other services you choose to use

- **Map tiles:** the App requests map tiles from the configured tile provider. That provider may receive technical information such as your IP address and the map areas requested.
- **Single sign-on:** if your Endurain server offers an SSO provider, the provider handles authentication according to its own privacy policy.
- **System share sheet:** when you export a GPX file, the App passes the file to the destination application you choose. That application's privacy policy applies to its handling of the file.
- **Apple HealthKit and Android Health Connect:** these platforms provide data only after you grant permission. Their respective platform terms and privacy policies apply.
- **Bluetooth sensors:** the App connects directly to a sensor you pair; no sensor data is sent anywhere except embedded in your recorded activity when uploaded to your selected Endurain server.
- **Remote crash reporting (opt-in):** if enabled, sanitized crash reports are sent only to Endurain's managed diagnostics service, never to a third party. Because reports aren't retained on-device after transmission, deleting a sent report requires contacting Endurain's team directly.

## Health Information

Health information is optional. The App accesses only the HealthKit or Health Connect categories that you authorize and uses them only to import and display workouts in your Endurain activity history.

The App does not use health information for advertising or marketing. It does not provide health information to data brokers. Health information is sent to your selected Endurain server only when you choose to import or upload the related activity through the App.

You can revoke the App's health permissions at any time in Apple Health or Android Health Connect. You can remove imported activities from the App's local history and manage server-side copies through your Endurain server.

## External Sensors

Bluetooth access is optional and used only to discover and connect to the heart-rate, power, or cadence sensor you choose to pair. You can revoke Bluetooth permission in your device settings, or unpair a sensor in the App's Sensors settings to remove its locally stored identifier at any time.

## Location Information

Location access is optional but required for location-based map features and GPS activity recording. You may grant approximate or precise location permission as supported by your device. Background location access is used only while an activity recording is active, so a route can continue when the App is in the background.

You can stop a recording, revoke location permission, or disable location services at any time in your device settings. Deleting an activity removes its local record and route file; manage any copy already uploaded to an Endurain server through that server.

## Retention and Deletion

The App retains local activity records, GPX files, preferences, and diagnostics until you delete them, clear the App's data, or uninstall the App. Authentication sessions can be cleared by signing out.

For information stored on an Endurain server, use the server's activity, account, and deletion controls or contact that server's operator. The App cannot delete data held by a server that it does not operate.

## Security

The App uses operating-system secure storage for authentication material and uses encrypted HTTPS connections when supported by the selected server. Because Endurain supports self-hosted servers, you may choose to connect to a server that permits an unencrypted HTTP connection. The App warns before using such a connection. Do not use HTTP for accounts or activity data that require confidentiality.

No method of electronic storage or transmission is completely secure. Protect your device and use a trusted, properly secured Endurain server.

## Children's Privacy

The App is not directed to children. Do not use the App if you are below the minimum age required to consent to personal-data processing in your country, unless a parent or legal guardian has provided consent where required.

## International Use

You choose the Endurain server that receives your data. That server may be located in a country different from yours. The server operator is responsible for explaining applicable international data transfers and legal bases for processing.

## Changes to This Policy

We may update this Privacy Policy to reflect changes to the App or applicable law. The current version will be published at this page, with an updated effective date.

## Contact

For questions about Endurain and this Privacy Policy, contact:

- **Email:** [joao@endurain.com](mailto:joao@endurain.com)

For questions about data held by a self-hosted Endurain server, contact that server's operator directly.