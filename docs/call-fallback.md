# If this computer is off or offline: send calls to a person

The agent runs on your own computer. Twilio sends every incoming call to the agent over the internet. If the computer is switched off, asleep or has lost its connection, Twilio cannot reach the agent and the caller hears nothing useful. Texts are different: Twilio keeps retrying them.

The fix lives in your Twilio account, not on your computer: Twilio's **fallback address**. When Twilio cannot reach the agent, it asks the fallback address what to do instead, and we set it up to ring your business phone.

Tested for real on 2026-10-19: with the agent stopped, a call to a Twilio number was forwarded by this fallback and the business phone rang within about 6 seconds.

This is **off by default**. Until you set it, a call that arrives while the computer is off is lost.

## Set it up (about 3 minutes)

1. In the agent dashboard open **Settings, Your business details** and check that **Customer service phone** is your real business line, with the country code, and is not your Twilio number.
2. Open **Connect, Texts and calls (Twilio)**. At the bottom, under **If this computer is off**, the dashboard shows a short block of text made with your phone number.
3. In Twilio open **Develop, TwiML Bins, Create new TwiML Bin**. Name it (for example "Call backup"), paste the text, and press Create.
4. Copy the URL Twilio shows for the bin and paste it into the dashboard box, then press **Save backup**. The agent sets it on your number for you. The line above the box changes to "Protected".

The text it generates says a short line, rings your business phone for up to 25 seconds, and says sorry if nobody picks up:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>Sorry, we cannot take your call on this line right now. Connecting you to our team.</Say>
  <Dial timeout="25">+15551234567</Dial>
  <Say>Sorry, nobody is available right now. Please try again later.</Say>
</Response>
```

If you want voicemail instead, replace the `<Dial>` line with `<Record maxLength="120" playBeep="true"/>`. Recordings then appear in your Twilio console under Monitor, Recordings. You will not be notified, so forwarding to a phone is the better default.

## Test it, safely

1. Stop the agent (close its window) or turn Wi-Fi off on the computer.
2. Call your Twilio number from another phone.
3. Your business phone should ring within a few seconds. Turn the agent back on afterwards.

## Honest limits

* Twilio asks the fallback when it cannot connect, times out, or gets an error from the agent. A computer that is on but very slow may still answer too late.
* The agent cannot ring your phone itself when it is off. This works because Twilio does it. If you cancel or break the TwiML Bin, the protection stops. The dashboard shows "Protected" only while your number points at the saved address.
* For a real business, an always-on machine (a small server or a cloud computer) plus this fallback is the safe setup.
* `sh sv-agent doctor` prints a note when Twilio is connected and no backup is set.
* Outgoing texts and calls the agent could not send while offline are queued and sent when it is back (see [offline-and-queue.md](offline-and-queue.md)). Incoming calls cannot be queued.
