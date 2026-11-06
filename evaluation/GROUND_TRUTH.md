# Evaluation pages

Single-file HTML fixtures for VerSimUX. Upload at most five `.html` files per run. Use `control-account.html` in a separate run to check false positives.

Each planted issue is something a persona can hit by trying the task. Do not upload this file.

## harbor-login.html

Task: sign in.

| ID | What a correct finding looks like | WCAG |
| --- | --- | --- |
| L1 | Page has no `lang` on `<html>` | 3.1.1 |
| L2 | No heading; "Sign in" is a `<div>` | 1.3.1 / 2.4.6 |
| L3 | `#subtitle` is `#c8c8c8` on white (about 1.7:1) | 1.4.3 |
| L4 | `#email` and `#password` have placeholder text only, no `<label>` | 1.3.1 / 3.3.2 |
| L5 | Tab order is password, then the eye control, then email (`tabindex` 1, 2, 3) | 2.4.3 |
| L6 | `#togglePw` is an empty button (no accessible name) | 4.1.2 |
| L7 | Inputs, eye button, submit, and the forgot link use `outline:none` | 2.4.7 |
| L8 | "Forgot?" is an 11px link, well under a 24px target | 2.5.8 |
| L9 | Submit with empty or wrong fields does nothing: `#status` stays empty | 3.3.1 |

## lumen-checkout.html

Task: pay for the oak lamp.

| ID | What a correct finding looks like | WCAG |
| --- | --- | --- |
| C1 | Product image has no `alt` (it shows "Oak lamp") | 1.1.1 |
| C2 | Card, expiry, and CVV inputs have placeholders only | 3.3.2 / 1.3.1 |
| C3 | Expiry gives no hint that the expected format is `MM/YY`; card gives no hint of 16 digits | 3.3.2 |
| C4 | Shipping note is `#b0b0b0` on white (about 2.2:1) | 1.4.3 |
| C5 | Terms control is a clickable `<div>`, not a checkbox, and it is not keyboard operable | 2.1.1 / 4.1.2 |
| C6 | Invalid card or expiry only turns the border red; no text error | 3.3.1 / 1.4.1 |
| C7 | Pay button is labelled "Continue", which does not say that it charges the card | clarity |
| C8 | Focus outline removed on the fields and the pay button | 2.4.7 |

## pulse-inbox.html

Task: open a message, or switch to Sent.

| ID | What a correct finding looks like | WCAG |
| --- | --- | --- |
| I1 | No `lang` on `<html>` | 3.1.1 |
| I2 | No headings; the inbox title is a styled `<div>` | 1.3.1 |
| I3 | Search, filter, and delete are 24px icon buttons whose only content is a symbol, with no text name | 4.1.2 / 2.5.8 |
| I4 | Inbox, Sent, and Archive are clickable `<div>`s, not links or buttons | 2.1.1 |
| I5 | Message rows are clickable `<div>`s | 2.1.1 |
| I6 | Sender/time lines are `#c5c5c5` on white (about 1.7:1) | 1.4.3 |
| I7 | The chart image uses `alt=""` but the graphic states "Unread this week: 18" | 1.1.1 |
| I8 | Icon buttons remove the focus outline | 2.4.7 |

## profile-modal.html

Task: edit the profile and save a phone number.

| ID | What a correct finding looks like | WCAG |
| --- | --- | --- |
| M1 | Dialog has no `role="dialog"`, no accessible name, and no `aria-modal` | 4.1.2 |
| M2 | After Edit profile, Tab never leaves the dialog, and Escape does not close it | 2.1.2 |
| M3 | Close control is a `<div>` showing ×, not a button, and it is not in tab order | 2.1.1 / 4.1.2 |
| M4 | Name and phone fields have no labels; phone has no format hint | 3.3.2 |
| M5 | A bad phone number only turns the border red | 3.3.1 / 1.4.1 |
| M6 | Focus outline removed inside the dialog | 2.4.7 |
| M7 | Header "Help" link is `#4a6a84` on `#16324f` (about 2.3:1) | 1.4.3 |

## clinic-booking.html

Task: book a visit. A valid date is `DD/MM/YYYY`. A valid mobile starts with `07`.

| ID | What a correct finding looks like | WCAG |
| --- | --- | --- |
| B1 | No `lang` on `<html>` | 3.1.1 |
| B2 | No heading element; "Book a visit" is a `<div>` | 1.3.1 |
| B3 | Banner image has `alt=""` but it says flu clinic walk-ins close at 16:00 | 1.1.1 |
| B4 | Name, date, and mobile are placeholder-only | 3.3.2 |
| B5 | Date and mobile give no format hint, and a failed submit shows no message | 3.3.1 / 3.3.2 |
| B6 | Tab order is date, Book, mobile, then name | 2.4.3 |
| B7 | Time slots are 28×28px and only show 9, 10, 13, 15 | 2.5.8 / clarity |
| B8 | The selected slot is shown only by a green fill (`#d7efe3`) close to white | 1.4.1 |
| B9 | Focus outline removed on inputs, slots, and Book | 2.4.7 |

## control-account.html

Task: save a UK mobile number. This page is the negative control. A correct run reports no accessibility defects here.

Expected behaviour: visible label, format hint, 44px target, focus ring, `role="alert"` on a bad number, `role="status"` on success, `lang="en"`, one `h1`, skip link.
