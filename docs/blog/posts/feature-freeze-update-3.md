---
draft: false
date: 2026-07-23
authors:
  - joaovitoriasilva
categories:
  - Project update
  - Maintenance
---

# Feature freeze update 3

This is the third update on feature-freeze progress. Before I start, have you already subscribed to Endurain's [newsletter](#newsletter), powered by [Keila](https://keila.io)? If not, you can subscribe at the end of this blog post.

Yesterday, we released v0.19.0, the first release in Endurain's new release cycle, which was announced in the previous blog post. We are not sure whether an August release will happen because of the holiday period, but beta releases for the upcoming v0.20.0 will take place during August.

For v0.19.0, you can check the changelog in the [release notes](https://codeberg.org/endurain-project/endurain/releases/tag/v0.19.0), but I will summarize some of it here:
- We fixed an authorization issue affecting activity media uploads. Under certain conditions, an authenticated user could upload media to an activity they did not own. The issue was reported responsibly by Christian Flaßkamp. Thank you for helping make Endurain safer. Users should update to the latest release;
- Endurain has a new frontend, rebuilt from scratch with the help of AI. This is where AI shines: it worked with the existing code and helped us refactor it into a better overall position. In the past, a new version could ship with broken functionality because a schema or another part of the frontend had not been updated to reflect API changes. Now, those changes go through CI, which reports a non-passing status so they no longer go unnoticed. The frontend is now fully type-checked, more modular, and provides the foundation for caching and other important future features. We also think it looks better, which is supported by some of your feedback. You will also see a visual hint in the frontend when a new version is available;
- We also introduced new [logos](https://codeberg.org/endurain-project/endurain/src/branch/master/logo) and [brand guidelines](https://docs.endurain.com/developer-guide/brand-and-ux-guidelines/). This gives Endurain a more mature and polished feel, making the product more cohesive overall;
- Some new environment variables were introduced, along with validation that alerts an instance administrator when a legacy or unused environment variable is in use;
- We made many backend fixes and, more importantly, defined a way forward for evolving the platform. More information is below;
- We also made some less visible improvements, including new CI logic, new tests, simplified setup for new instances, and documentation fixes that improve the overall experience.

You can also check out our new [website](https://endurain.com).

<!-- more -->

## Mobile app

Progress on Endurain's official mobile app is also good. If you are in the Discord channel, you may already have tested the Android version. I have just had my Apple Developer account approved, so the iOS version should be available soon as well. We plan to price the app at EUR 4.99 plus VAT to support the project. If the project grows enough to allow us to make the app free, we will be happy to do so. The mobile app will also introduce **opt-in** remote crash reporting, sending errors to a self-hosted GlitchTip instance so that we can detect and fix them. For the time being, we will keep the repository private, but that may change in the future. We are still assessing the best way forward. We would like your feedback, which you can provide in this [form](https://forms.cloud.microsoft/r/TCp7zaR9Uj).

## Endurain merch

We are exploring the launch of official Endurain gear and merchandise to help promote and support the project. We have not defined anything yet, but we would like your feedback. You can share it through this [form](https://forms.office.com/r/VHxLtdkMVj).

## Going forward

As mentioned previously, we have defined the next steps for the rework. They will consist of the following:
- Move to an event-driven architecture:
  - This will allow the service to grow to multiple nodes when needed, with Redis, S3, and pub/sub support;
  - We do not want to break existing instances or introduce unnecessary complexity, so this additional overhead will be optional. For a single-node setup, as it works today, processing will happen in memory and use local storage without changes;
  - We are aiming for a unified codebase that adapts based on your setup;
  - We will start with the activities module. In v0.20.0, we will introduce a refactored activity-ingestion flow built on this architecture.
- Jobs notion, so jobs (activity import, bulk, Strava, Garmin, thumbnail genaration, others) can be tracked, redone if failed, and others scenarios;
- Ensure that nothing blocks the main API thread, which will provide a better experience for end users;
- Improve scalability and modularity so that new additions and contributor onboarding are faster and simpler because the code is better organized;
- Assess separating some logic into its own library, as we do today with [safeuploads](https://codeberg.org/endurain-project/safeuploads);
- After the backend is reworked around this architecture, we plan to introduce activity likes and comments. What comes next remains undefined.

## Thank you note

Thank you to everyone who uses, tests, reports issues, translates, sponsors, or contributes to Endurain.

## Newsletter

--8<-- "_snippets/newsletter.html"
