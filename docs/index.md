<div align="center">
  <p>
    <img src="assets/logo.svg" width="150" height="150">
  </p>

  <p>
    <a href="https://crowdin.com/project/endurain">
      <img src="https://badges.crowdin.net/endurain/localized.svg" alt="Crowdin">
    </a>
    <img src="https://img.shields.io/github/license/joaovitoriasilva/endurain" alt="License">
    <a href="https://github.com/joaovitoriasilva/endurain/releases">
      <img src="https://img.shields.io/github/v/release/joaovitoriasilva/endurain" alt="GitHub release">
    </a>
    <a href="https://github.com/joaovitoriasilva/endurain/stargazers">
      <img src="https://img.shields.io/github/stars/joaovitoriasilva/endurain.svg?style=social&label=Star" alt="GitHub stars">
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
- **Backend:** Python FastAPI, Alembic, SQLAlchemy, stravalib and python-garminconnect for Strava and Garmin Connect integration, gpxpy and fitdecode for .gpx and .fit file import respectively 
- **Database:** MariaDB or PostgreSQL for efficient data management
- **Observability:** Jaeger for basic tracing and monitoring

To deploy Endurain, a Docker image is available, and a comprehensive example can be found in the "docker-compose.yml.example" file provided in the project repository. Configuration is facilitated through environment variables, ensuring flexibility and ease of customization.

## Developer's Note

As a non-professional developer, my journey with Endurain involved learning and implementing new technologies and concepts, with invaluable assistance from ChatGPT. The primary motivation behind this project was to gain hands-on experience and expand my understanding of modern development practices. Second motivation is that I'm an amateur triathlete and I want to keep track of my gear and gear components usage.

If you have any recommendations or insights on improving any aspect of Endurain, whether related to technology choices, user experience, or any other relevant area, I would greatly appreciate your input. The goal is to create a reliable and user-friendly fitness tracking solution that caters to the needs of individuals who prefer self-hosted applications. Your constructive feedback will undoubtedly contribute to the refinement of Endurain.

## Features

Endurain currently supports:

- Multi-user functionality with admin and user profiles adaptable interfaces
- Activity import via manual or bulk upload (.gpx and .fit files. .fit files are preferred)
- Strava integration for syncing activities and gear
- Garmin Connect integration for syncing activities, gear and body composition
- Activity feeds and statistics (week/month)
- Basic activity privacy settings
- Gear tracking (wetsuits, bicycles, shoes, racquets)
- Default gear for activity types
- User pages with stats and activity histories
- Follower features (view activities)
- Multi-language support
- Imperial and metric units support
- Dark/light theme switcher
- Third-party app support
- Weight logging

## Planned Features

Upcoming features (in no particular order):

- Live tracking
- Gear component tracking (e.g., track when components like bike chains need replacing)
- Activity comments and likes
- Notification system
- Potential ActivityPub integration

## Sponsors

A huge thank you to the project sponsors! Your support helps keep this project going.

Consider [sponsoring Endurain on GitHub](https://github.com/sponsors/joaovitoriasilva) to ensure continuous development.

## Contributing

Contributions are welcomed! Please open an issue to discuss any changes or improvements before submitting a PR. Check out the [Contributing Guidelines](https://github.com/joaovitoriasilva/endurain/blob/master/CONTRIBUTING.md) for more details.

## License

This project is licensed under the AGPL-3.0 or later License.

## Help Translate

Endurain has multi-language support, and you can help translate it into more languages via [Crowdin](https://crowdin.com/project/endurain). 

Currently supported in:

 - Catalan by [@rubenixnagios](https://github.com/rubenixnagios)
 - German by [@ThreeCO](https://github.com/ThreeCO)
 - French (FR) [@gwenvador](https://github.com/gwenvador)
 - Dutch (NL) [@woutvanderaa](https://github.com/woutvanderaa)
 - Portuguese (PT)
 - Spanish (ES) [@rgmelkor](https://github.com/rgmelkor)
 - English (US)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=joaovitoriasilva/endurain&type=Date)](https://star-history.com/#joaovitoriasilva/endurain&Date)