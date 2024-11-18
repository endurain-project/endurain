<div align="center">
  <img src="frontend/app/public/logo/logo.png" width="128" height="128">

  # Endurain

  <a title="Crowdin" target="_blank" href="https://crowdin.com/project/endurain"><img src="https://badges.crowdin.net/endurain/localized.svg"></a>
  ![License](https://img.shields.io/github/license/joaovitoriasilva/endurain)
  [![GitHub release](https://img.shields.io/github/v/release/joaovitoriasilva/endurain)](https://github.com/joaovitoriasilva/endurain/releases)
  [![GitHub stars](https://img.shields.io/github/stars/joaovitoriasilva/endurain.svg?style=social&label=Star)](https://github.com/joaovitoriasilva/endurain/stargazers)

  **A self-hosted fitness tracking service**  
  Visit Endurain's [Mastodon profile](https://fosstodon.org/@endurain).

  <img src="screenshot_01.png" alt="Endurain Screenshot">
</div>

## Table of Contents

- <a href="https://docs.endurain.com">Endurain documentation</a>
- [What is Endurain?](#what-is-endurain)
- [Sponsors](#sponsors)
- [Contributing](#contributing)
- [License](#license)
- [Help Translate](#help-translate)

## What is Endurain?

Endurain is a self-hosted fitness tracking service designed to give users full control over their data and hosting environment. It's similar to Strava but focused on privacy and customization. Built with:

- **Frontend:** Vue.js and Bootstrap CSS
- **Backend:** Python FastAPI, Alembic, SQLAlchemy, stravalib for Strava integration, gpxpy and fitdecode for .gpx and .fit file import respectively 
- **Database:** MariaDB for efficient user data management
- **Observability:** Jaeger for basic tracing and monitoring

To deploy Endurain, Docker images are available, and a comprehensive example can be found in the "docker-compose.yml.example" file provided. Configuration is facilitated through environment variables, ensuring flexibility and ease of customization. More details bellow.

For more information please see the Endurain's [documentation](https://docs.endurain.com).

## Sponsors

A huge thank you to our sponsors! Your support helps keep this project going.

Consider [sponsoring Endurain on GitHub](https://github.com/sponsors/joaovitoriasilva) to ensure continuous development.

## Contributing

Contributions are welcomed! Please open an issue to discuss any changes or improvements before submitting a PR. Check out the [Contributing Guidelines](CONTRIBUTING.md) for more details.

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## Help Translate

Endurain has multi-language support, and you can help translate it into more languages via [Crowdin](https://crowdin.com/project/endurain). Currently, only English is available.