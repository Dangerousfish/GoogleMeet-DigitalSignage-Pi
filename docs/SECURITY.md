# Security Considerations

This project integrates with Google Workspace using a service account with
domain‑wide delegation. To protect your organisation and users, adhere to
the following security best practices.

## Protect the service‑account key

The file `service-account.json` contains credentials that allow your
application to impersonate a user and access room calendars. Treat it as
a secret:

* Store the file outside your repository and add it to `.gitignore`.
* Restrict file permissions (`chmod 600`).
* Do not share it via chat, email or commit it to Git.
* Rotate the key periodically via the Google Cloud console.

## Use least privilege

The service account needs only two OAuth scopes:

```
https://www.googleapis.com/auth/admin.directory.resource.calendar.readonly
https://www.googleapis.com/auth/calendar.freebusy
```

Avoid requesting broader scopes (e.g. full Calendar read or write).

## Restrict impersonation

Configure domain‑wide delegation so that the service account can impersonate
only a dedicated user with minimal rights (e.g. a generic "room signage"
account). Do not impersonate a super admin if it isn’t necessary.

## Network isolation

Run the signage backend on `127.0.0.1` or behind a firewall. The kiosk
should communicate with the backend via localhost. Avoid exposing the
service publicly without authentication.

## Keep the Pi up to date

Apply security updates regularly on the Raspberry Pi. For unattended
installations, consider enabling automatic updates via `apt`.

## Logging and privacy

The application intentionally uses the FreeBusy API to avoid collecting
meeting details. Do not log or display titles, attendee lists or other
private meeting data.