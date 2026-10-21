# Send email from your own mailbox

The agent can send emails (confirmations, follow-ups) from your Gmail, Outlook, Yahoo or your own domain. Free; it uses your mailbox's normal limits. You cannot use your normal password for this: you create a special app password.

## Gmail
1. Sign in at myaccount.google.com and open **Security**.
2. Switch on **2-Step Verification** if it is off (app passwords need it).
3. Search the page for **App passwords** (myaccount.google.com/apppasswords). Type a name such as "Speakvora agent" and press Create.
4. Google shows a 16-letter password once. Copy it.
5. In the agent open **Connect, Email** and fill in:
   - Mail server: `smtp.gmail.com`
   - Port: `465`
   - Username: your full Gmail address
   - Password: the 16-letter app password
   - Send from: for example `Your Business <you@gmail.com>`
6. Press **Test and email me**, type your address, and check your inbox.
Google Workspace accounts work the same way if the administrator allows app passwords.

## Outlook.com / Hotmail
1. Sign in at account.microsoft.com, open **Security, Advanced security options**, and switch on two-step verification.
2. In the same place choose **Create a new app password** and copy it.
3. In the agent: server `smtp-mail.outlook.com`, port `587`, your full address as the username, the app password, and Send from your address.

## Microsoft 365 (work account)
1. Ask your administrator to allow **Authenticated SMTP** for your mailbox (Microsoft 365 admin center, Users, your user, Mail, Manage email apps).
2. If you use multi-factor sign-in, create an app password if your organisation allows them.
3. In the agent: server `smtp.office365.com`, port `587`, your full address, your password or app password.

## Yahoo / iCloud
Create an app password in the account security settings (Yahoo: Account security, Generate app password; iCloud: appleid.apple.com, Sign-In and Security, App-Specific Passwords). Servers: `smtp.mail.yahoo.com` port 465; `smtp.mail.me.com` port 587.

## If something is wrong
- "Not accepted" or "hung up": the password is wrong or you used your normal password. Make a new app password.
- Emails land in spam: send a few to yourself first and mark them Not spam; add a clear subject.
