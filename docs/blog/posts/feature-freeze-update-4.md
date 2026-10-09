---
draft: false
date: 2026-10-09
authors:
  - joaovitoriasilva
categories:
  - Project update
  - Maintenance
---

# Feature freeze update 4

This is the fourth update on feature-freeze progress. Before I start, have you already subscribed to Endurain's [newsletter](#newsletter), powered by [Keila](https://keila.io)? If not, you can subscribe at the end of this blog post.

These past months have been slow when it comes to Endurain's development. Vacations, life, family, etc., made focusing on Endurain a little harder. However, I believe I'll have time to work on it over the next two months.

Some details below.

<!-- more -->

## Going back to GitHub

If you are on Discord, you have seen this text, nevertheless here it is.

Since moving Endurain to Codeberg, we ran into some real problems:
- We've been hit with repeated availability problems, especially with SSH access, Codeberg going down, and commit operations failing as a result. This was starting to actively slow down development, especially since we do this in our free time;
- It may be our lack of knowledge, but we had to configure a Forgejo Runner in order to build ARM64 images and to run some actions that were hitting Codeberg time limits. That's okay overall, however once again we got hit with some issues on the runner, sometimes we had to reboot, images would not build, the Android APK sometimes built successfully and sometimes didn't. And once again this was time we were spending on troubleshooting this instead of working on Endurain's development.
- Codeberg e.V. members recently voted through changes discouraging/prohibiting projects that are "written and maintained with heavy use of LLMs" or that accept LLM-generated contributions without oversight (details: https://blog.codeberg.org/protecting-our-floss-commons-from-llms.html). Endurain uses AI tooling in development and we accept AI-assisted PRs from contributors. Given that, we don't feel confident we're compliant with the new terms, and we don't want to keep the project somewhere it isn't clearly welcome. We also feel the terms are somewhat vague and open to interpretation depending on circumstances, meaning Endurain might be fine under them today, but not tomorrow.

Before anything else, we want to be clear, we genuinely like Codeberg's mission. Open source, community-run, Europe-based. It felt like the perfect home for Endurain, and I am actually a Codeberg e.V. member. We understand the reasoning behind the ToU changes and honestly agree with a lot of it. We also get that keeping an SLA when you're a community-owned, volunteer-run platform isn't easy, and we don't hold that against them.

We have now moved back to GitHub. We already used GitHub as a backup for Codeberg, so the main lift was just migrating issues and possibly PRs, not the whole repo. To be honest, our experience with GitHub hasn't been flawless either, for what it's worth, my account was blocked for 3 weeks with no explanation. But at the end of the day, we want to spend our time and energy building Endurain, not worrying about platform reliability or compliance ambiguity. Kind of the classic "it's not you, it's me" situation.

We know self-hosting (Forgejo/Gitea, etc.) comes up whenever this topic does, but we've decided against it. We would love to go down this path, but it would be a real burden for us to maintain, and it would take away precious time from developing Endurain. We had issues with a single runner, imagine a whole instance. We also want to explore some ideas we have for Endurain.

The migration is done, v0.19.3 has already been released from GitHub.

## Mobile app

The mobile app is out there in the wild, already being used by several Endurain users! The app functions well and does what it states, however it still has some things to get better. It is now free on the stores, we dropped the paid route, and it is available on Apple [TestFlight](https://testflight.apple.com/join/BjZ4DWPa) and Google closed beta. We are trying to get it to open beta for Android.

To join the closed beta on Android, here are the steps:
- Join the Google group [here](https://groups.google.com/g/endurain-test-group)
- Join the closed beta after you have been accepted into the group (it should be automatic) [here](https://play.google.com/apps/testing/com.endurain.endurain)
- Then install the app

The app repo is available [here](https://github.com/endurain-project/endurain-flutter), which is also on GitHub.

## Supporting libraries

As stated in the previous blog post, some work was being done to split some logic into their own libraries. We did this, but why did we go this route? More things to maintain right? Yes, however some parts of the code were starting to be its own thing, trying to solve some specific things that are not only an Endurain problem. Any other application might need to do file sanitization on uploads, authenticate users, handle storage, etc., so by going this route we give something back to the community. The implementation in theory can get better, because it solves a specific problem, more devs may adopt them, improve them, etc.

So we already had [safeuploads](https://github.com/endurain-project/safeuploads) and we now also have:
- [jasil](https://github.com/endurain-project/jasil) - Just Another Substrate & Infrastructure Library, a framework-agnostic infrastructure substrate for Python services: swappable capability backends, an event pipeline, durable jobs, and observability.
- [jafaal](https://github.com/endurain-project/jafaal) - Just Another FastAPI Authentication Library, a batteries-included, embedded FastAPI authentication library and a standards-shaped authorization server for applications controlled by one host.

jasil will be included in the upcoming 0.20.0 release, bringing the first iteration of the refactor to an event-driven architecture. We aim it to release this month, but once again, life may happen.

## Endurain merch

We are exploring the launch of official Endurain gear and merchandise to help promote and support the project. We have not defined anything yet, but we would like your feedback. You can share it through this [form](https://forms.office.com/r/VHxLtdkMVj).

## Thank you note

Thank you to everyone who uses, tests, reports issues, translates, sponsors, or contributes to Endurain.

## Newsletter

--8<-- "_snippets/newsletter.html"
