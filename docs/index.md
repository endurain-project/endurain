<div align="center">
  <p>
    <img src="assets/logo.svg" width="150" height="150">
  </p>

  <p>
    <a href="https://crowdin.com/project/endurain">
      <img src="https://badges.crowdin.net/endurain/localized.svg" alt="Crowdin">
    </a>
    <img src="https://img.shields.io/github/license/endurain-project/endurain" alt="License">
    <a href="https://github.com/endurain-project/endurain/releases">
      <img src="https://img.shields.io/github/v/release/endurain-project/endurain" alt="GitHub release">
    </a>
    <a href="https://github.com/endurain-project/endurain/stargazers">
      <img src="https://img.shields.io/github/stars/endurain-project/endurain.svg?style=social&label=Star" alt="GitHub stars">
    </a>
    <a href="https://github.com/endurain-project/endurain/blob/master/TRADEMARK.md">
      <img src="https://img.shields.io/badge/trademark-Endurain%E2%84%A2-blue" alt="Trademark Policy">
    </a>
  </p>

  <h2>
      Endurain
  </h2>
  <p>
    A self-hosted fitness tracking service - <a href="https://fosstodon.org/@endurain">Mastodon profile</a> - <a href="https://discord.gg/6VUjUq2uZR">Discord server</a>
  </p>
</div>

## What is Endurain?

Endurain is a self-hosted fitness tracking service designed to give users full control over their data and hosting environment. Built with:

- **Frontend:** Vue.js, Notivue and Bootstrap CSS
- **Backend:** Python FastAPI, Alembic, SQLAlchemy, Apprise, stravalib and python-garminconnect for Strava and Garmin Connect integration, gpxpy, tcxreader and fitdecode for .gpx, .tcx and .fit file import respectively 
- **Database:** PostgreSQL for efficient data management
- **Observability:** Jaeger for basic tracing and monitoring

To deploy Endurain, a Docker image is available, and a comprehensive example can be found in the "docker-compose.yml.example" file provided in the project repository. Configuration is facilitated through environment variables, ensuring flexibility and ease of customization.

## Developer's Note

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

## Planned Features

Please visit the [ROADMAP.md file on GitHub](https://github.com/endurain-project/endurain/blob/master/ROADMAP.md).

## Sponsors

A huge thank you to the project sponsors! Your support helps keep this project going.

Consider [sponsoring Endurain on GitHub](https://github.com/sponsors/joaovitoriasilva) to ensure continuous development.

## Contributing

Contributions are welcomed! Please open an issue to discuss any changes or improvements before submitting a PR. Check out the [Contributing Guidelines](https://github.com/endurain-project/endurain/blob/master/CONTRIBUTING.md) for more details.

## License

This project is licensed under the AGPL-3.0 or later License.

## Help Translate

Endurain has multi-language support, and you can help translate it into more languages via [Crowdin](https://crowdin.com/project/endurain). 

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

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=endurain-project/endurain&type=Date)](https://star-history.com/#endurain-project/endurain&Date)

## Trademark Notice

Endurain® is a trademark of João Vitória Silva.  

You are welcome to self-host Endurain and use the name and logo, including for personal, educational, research, or community (non-commercial) use.  
Commercial use of the Endurain name or logos (such as offering paid hosting, products, or services) is **not permitted without prior written permission**.

See [`TRADEMARK.md`](https://github.com/endurain-project/endurain/blob/master/TRADEMARK.md) for full details.

<div align="center">
  <sub>Built with ❤️ from Portugal | Part of the <a href="https://github.com/endurain-project">Endurain</a> ecosystem</sub>
</div>