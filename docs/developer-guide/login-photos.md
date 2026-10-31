# Suggesting a login photo

Anyone can suggest a photo for the Endurain login page. To keep the project free to redistribute, every accepted photo must be licensed so that Endurain, its forks and its releases can use it without restriction.

## How to submit

1. Open an issue with the [Login photo suggestion](https://github.com/endurain-project/endurain/issues/new?template=login_photo_suggestion.md) template.
2. Attach the photo, add an optional description, and tick the authorship confirmations.
3. Choose exactly one license and tick its box.

Submissions without a license box ticked are closed without review.

## Licenses

| License | Effect |
| ------- | ------ |
| [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) (preferred) | You dedicate the photo to the public domain. Where the law does not allow that, you grant everyone a perpetual, irrevocable, worldwide, royalty-free license. No credit is required. |
| [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Anyone may use the photo, including commercially, as long as they credit you. Endurain lists your name in the credits. |

Both choices are irrevocable. Pick CC BY only if you want to be credited.

## Requirements

- You took the photo yourself and are its only author.
- It is not AI-generated and not based on someone else's work.
- It shows no identifiable people, trademarks or logos. A copyright license does not cover privacy or personality rights.
- Photos from stock sites such as Unsplash or Pexels are not accepted, because their licenses do not allow redistributing the file on its own.
- Strip EXIF data, including GPS coordinates, before uploading.
- Landscape orientation, at least 1920x1080.

## For maintainers

When accepting a photo:

1. Download the original file from the issue. Attachment URLs can change, so do not link to them.
2. Check the issue for the ticked license and authorship boxes.
3. Add the photo to [`frontend/src/assets/CREDITS.md`](https://github.com/endurain-project/endurain/blob/master/frontend/src/assets/CREDITS.md) with its author, license and issue link. CC BY photos require the credit.
4. Reference the issue in the commit message, so the consent stays linked to the file.

This page is not legal advice.
