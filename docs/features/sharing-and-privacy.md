# Sharing, privacy and followers

Endurain is private by default. Profiles are never public: only individual activities can be shared, and only in the ways described here.

## Who can see an activity

Every activity has a **visibility**:

| Visibility | Who sees it |
| ---------- | ----------- |
| Public | Anyone with a link, including people who are not signed in, when the server allows public links (see below). |
| Followers | You and the users whose follow request you accepted. |
| Private | Only you. |

Set the default for new activities in **Settings → My profile → Privacy → Default activity visibility**. It applies to new activities only. To change the activities you already have, use **Existing activities visibility**, which updates every activity in your account after a confirmation. You can also change one activity from its edit dialog.

## Hiding details

For activities that others can see, you can hide individual details: start time, location, map, heart rate, power, cadence, elevation, speed, pace, laps, workout sets and steps, and gear. Set your defaults under **Hide from shared activities** in your privacy settings. New activities, including imported ones, get these defaults. Each activity can override them in its edit dialog under **Hide from others**.

Hidden details are removed from what followers and public viewers receive. You always see your own activities in full.

An activity can also be hidden from everyone with **Hide this activity from everyone**. Endurain uses this itself when an import looks like a duplicate (see [Duplicate detection](importing.md#duplicate-detection)); you can switch it off in the activity's edit dialog if the activity is not a duplicate.

## Public links

Public links are controlled by an administrator in **Settings → Server settings → Sharing**:

- **Enable public shareable links:** off by default. When on, anyone with the link to a *public* activity can view it without signing in.
- **Show user info on public links:** when on, the link also shows the owner's name and profile photo.

An activity is served to anonymous visitors only if all of these hold: public links are enabled, the activity's visibility is public, and the activity is not hidden. Its laps, sets, streams and workout steps are served only if those details are not hidden. For anyone who may not see an activity, Endurain answers as if it did not exist, so nobody can find out which activity ids exist.

!!! warning
    Anyone who has a public link can open it and pass it on. Treat a public activity as published.

## Followers

Following is by request:

1. A user requests to follow you. You get a notification.
2. You accept or reject the request. Until you accept, the request is pending and they see nothing extra.
3. Accepted followers can see your activities with visibility Followers or Public, with your hidden details removed.

You can remove a follower at any time. Your follower and following lists are visible only to you and to your accepted followers, and nobody else can list them.

## For administrators

- Public links are off until you enable them in server settings. Review the "user info" option before turning it on.
- Sign-up approval, email verification and password rules are in the same settings page.
- Users can export their own data; see [Exporting and importing your data](export-import.md).
