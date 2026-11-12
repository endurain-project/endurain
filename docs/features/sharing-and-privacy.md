# Sharing, privacy and followers

Endurain is private by default: new activities are Private until you choose otherwise. There is no public profile page. Other people on your server see only your name, username, city and photo, plus the activities you made visible to them, in the ways described here.

## Who can see an activity

Every activity has a **visibility**:

| Visibility | Who sees it |
| ---------- | ----------- |
| Public | Every signed-in user on this server, including on your profile's activity list and stats, and anyone with a link, even without signing in, when the administrator has enabled public links (see below). |
| Followers | You and the users whose follow request you accepted. |
| Private | Only you. |

Set the default for new activities in **Settings → My profile → Privacy → Default activity visibility**. It is Private for new accounts. It applies to new activities only. To change the activities you already have, use **Existing activities visibility**, which updates every activity in your account after a confirmation. You can also change one activity from its edit dialog.

## Hiding details

For activities that others can see, you can hide individual details: start time, location, map, heart rate, power, cadence, elevation, speed, pace, laps, workout sets and steps, and gear. Set your defaults under **Hide from shared activities** in your privacy settings. New activities, including imported ones, get these defaults. Each activity can override them in its edit dialog under **Hide from others**.

Hidden details are removed from what followers and public viewers receive. Hiding the location also hides the activity's time zone, so times are then shown in the viewer's own zone. Ids that tie an activity to a provider account (Garmin Connect, Strava) and the record of how it was imported are never shown to others, whatever you hide. You always see your own activities in full.

An activity can also be hidden from everyone with **Hide this activity from everyone**. Endurain uses this itself when an import looks like a duplicate (see [Duplicate detection](importing.md#duplicate-detection)); you can switch it off in the activity's edit dialog if the activity is not a duplicate.

## Finding people

Signed-in users find each other by username in **Search**. A search needs at least 3 characters, and there is no way to list every user without one. It shows one page of matches, sized by the server's records-per-page setting. Switch off **Let others find me in search** in your privacy settings to stay out of the results; it is on by default. Your profile can still be opened from a direct link, and the activities you made visible still follow the table above. Inactive accounts and accounts awaiting approval are never listed or shown.

## Public links

Public links are controlled by an administrator in **Settings → Server settings → Public sharing**:

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

You can block a user from their profile or from **Settings → My profile → Blocked users**: they can no longer ask to follow you, every follow between you is removed and they are not told. After you decline a follow request, the same person cannot ask again for 7 days. You can remove a follower at any time. Your follower and following lists are visible only to you and to your accepted followers, and nobody else can list them.

## For administrators

- Public links are off until you enable them in server settings. Review the "user info" option before turning it on.
- Sign-up approval, email verification and password rules are in the same settings page.
- Users can export their own data; see [Exporting and importing your data](export-import.md).
