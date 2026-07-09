<div align="center">
  <p>
    <img class="index-logo" src="assets/brand_logo_light_theme.png" width="150" height="150">
  </p>

  <p>
    <a href="https://translate.codeberg.org/engage/endurain/"><img src="https://translate.codeberg.org/widget/endurain/svg-badge.svg" alt="Translation status"></a>
    </a>
    <img src="https://img.shields.io/badge/license-AGPL%20v3-blue" alt="License">
    <a href="https://codeberg.org/endurain-project/endurain/releases">
      <img src="https://img.shields.io/badge/dynamic/json?url=https://codeberg.org/api/v1/repos/endurain-project/endurain/releases/latest&query=$.tag_name&label=release&color=blue" alt="Latest Release">
    </a>
    <a href="https://codeberg.org/endurain-project/endurain">
      <img src="https://img.shields.io/badge/dynamic/json?url=https://codeberg.org/api/v1/repos/endurain-project/endurain&query=$.stars_count&label=stars&logo=codeberg" alt="Stars">
    </a>
    <a href="https://codeberg.org/endurain-project/endurain/blob/master/TRADEMARK.md">
      <img src="https://img.shields.io/badge/trademark-Endurain%E2%84%A2-blue" alt="Trademark Policy">
    </a>
  </p>

  <h2>
      Endurain
  </h2>
  <p>
    A self-hosted fitness tracking service - <a href="https://fosstodon.org/@endurain">Mastodon profile</a> - <a href="https://discord.gg/6VUjUq2uZR">Discord server</a> - <a href="#newsletter">Newsletter</a>
  </p>
</div>

## 🚀 Try the Demo

Experience Endurain without installation:

**Demo URL:** [https://demo.endurain.com](https://demo.endurain.com)

- **Username:** `admin`
- **Password:** `admin`
- **Reset Schedule:** Daily at midnight (Europe/Lisbon timezone)

!!! warning "Demo Environment"
    The demo environment resets every day at midnight. Do not store important data or expect persistence.

## What is Endurain?

Endurain is a self-hosted fitness tracking service designed to give users full control over their data and hosting environment. Built with:

- **Frontend:** Vue.js 3 with TypeScript, Tailwind CSS and shadcn-vue components, with Pinia and TanStack Query for state management
- **Backend:** Python FastAPI, Alembic, SQLAlchemy, Apprise, stravalib and python-garminconnect for Strava and Garmin Connect integration, gpxpy, tcxreader and fitdecode for .gpx, .tcx and .fit file import respectively 
- **Database:** PostgreSQL for efficient data management

To deploy Endurain, a Docker image is available, and a comprehensive example can be found in the "docker-compose.yml.example" file provided in the project repository. Configuration is facilitated through environment variables, ensuring flexibility and ease of customization.

## Developer's note

As a non-professional developer, my journey with Endurain involved learning and implementing new technologies and concepts, with invaluable assistance from GitHub Copilot and ChatGPT. The primary motivation behind this project was to gain hands-on experience and expand my understanding of modern development practices. Second motivation is that I'm an amateur triathlete and I want to keep track of my gear and gear components usage.

If you have any recommendations or insights on improving any aspect of Endurain, whether related to technology choices, user experience, or any other relevant area, I would greatly appreciate your input. The goal is to create a reliable and user-friendly fitness tracking solution that caters to the needs of individuals who prefer self-hosted applications. Your constructive feedback will undoubtedly contribute to the refinement of Endurain.

## Features

Endurain currently supports:

- Multi-user functionality with admin and user profiles adaptable interfaces
- Activity import via manual or bulk upload (.gpx, .tcx and .fit files. .fit files are preferred)
- Strava integration for syncing activities and gear
- Garmin Connect integration for syncing activities, gear and body composition
- Activity feeds and statistics (week/month)
- Basic activity privacy settings
- Gear tracking (wetsuits, bicycles, shoes, racquets, skis, snowboards)
- Gear component tracking (e.g., track when components like bike chains need replacing)
- Default gear for activity types
- User pages with stats and activity histories
- Follower features (view activities)
- Multi-language support
- Imperial and metric units support
- Dark/light theme switcher
- Third-party app support
- Weight, steps and sleep logging
- Notification system
- Define and track goals
- MFA TOTP support
- Password reset through email link. Uses Apprise for email notifications
- Sign-up with configurable email verification and admin approva
- SSO support (OIDC/SAML)

## Planned features

Please visit the [ROADMAP.md file on Codeberg](https://codeberg.org/endurain-project/endurain/src/branch/master/ROADMAP.md).

## Sponsors

A huge thank you to the project sponsors! Your support helps keep this project going.

Support Endurain's development on:

- [Buy Me a Coffee](https://buymeacoffee.com/endurain)
- [liberapay](https://liberapay.com/endurain/)
- [Patreon](https://patreon.com/u84745218)
- [GitHub Sponsors using archived repo](https://github.com/endurain-project/endurain)

## Contributing

Contributions are welcomed! Please open an issue to discuss any changes or improvements before submitting a PR. Check out the [Contributing Guidelines](https://codeberg.org/endurain-project/endurain/blob/master/CONTRIBUTING.md) for more details.

## License

This project is licensed under the AGPL-3.0 or later License.

## Help translate

Endurain has multi-language support, and you can help translate it into more languages via [Codeberg Translate](https://translate.codeberg.org/projects/endurain/). 

Currently supported in:

 - Catalan by [@rubenixnagios](https://github.com/rubenixnagios)
 - Chinese Simplified
 - Chinese Traditional
 - German by [@ThreeCO](https://github.com/ThreeCO)
 - French (FR) [@gwenvador](https://github.com/gwenvador)
 - GALICIAN (GL)
 - Dutch (NL) [@woutvanderaa](https://github.com/woutvanderaa)
 - Portuguese (PT)
 - Slovenian (SL) [@thehijacker](https://github.com/thehijacker)
 - Spanish (ES) [@rgmelkor](https://github.com/rgmelkor) and [@tinchodin](https://github.com/tinchodin)
 - English (US)

## Trademark notice

Endurain® is a trademark of João Vitória Silva.  

You are welcome to self-host Endurain and use the name and logo, including for personal, educational, research, or community (non-commercial) use.  
Commercial use of the Endurain name or logos (such as offering paid hosting, products, or services) is **not permitted without prior written permission**.

See [`TRADEMARK.md`](https://codeberg.org/endurain-project/endurain/blob/master/TRADEMARK.md) for full details.

## Newsletter

--8<-- "_snippets/newsletter.html"

<div align="center">
  <sub>Built with ❤️ from Portugal | Part of the <a href="https://codeberg.org/endurain-project">Endurain</a> ecosystem</sub>
</div>