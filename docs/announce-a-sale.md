# Announce a sale

For shops, online stores and marketplace sellers, restaurants and food trucks, salons, spas and fitness studios, laundries and dry cleaners, and car businesses. **It is never offered** to clinics, hospitals, pharmacies, dispensaries, law firms, finance, collections, public services, schools or prisons, and the agent refuses to run it there even if someone edits a file.

## What happens
1. **It watches.** You list up to five public web pages (your sale page, your home page) and, if you have one, a product list (JSON or CSV with a normal price and a sale price). Once a day, and when you press **Check now**, the agent looks for sale words (such as "sale", "% off", "clearance", "buy one get one") that were not there last time. The first look only learns what is there.
2. **It writes a draft.** From the words on that page only: it never makes up a price, a date or a promise. It shows the draft on your dashboard and tells your team on Slack or Teams. Nothing is sent.
3. **You check it.** Change the words, press **Preview** to see exactly what customers receive (your business name, your text, "Reply STOP to opt out"), who would get it and who is left out, and **Send me a test** to get it on your own phone first.
4. **You approve.** Only then does it go out, and only to **people who agreed to sale texts**, in small batches within your hourly limit and inside your sending hours (default 9 a.m. to 8 p.m. in your time zone). Anyone who already got your most sale texts for the month (default four) is skipped. If the text is changed after approval, the run stops and asks again.
5. **Practice mode rehearses it.** While you are in Practice mode (the default) the whole run is done as a rehearsal: you see who would have received it, and nothing is sent.

## The consent list
Each person on the list has a **phone number, how they agreed and when**. A person with no source or no time is not added. Ways to build it:
* **Add one person** (for example from a counter sign-up sheet) or **import a list** (CSV with columns `phone, source, date, name`; rows without a source or a date are refused and listed);
* customers **text DEALS** to your number and are added with "texted DEALS to our number" and the time;
* anyone who replies **STOP** leaves the list for good and is never texted again. Texting START does not bring them back; only a new DEALS from them does.

## Honest about the rules
Texting people who have not agreed to sale texts can break the law and mobile carrier rules, and can cost far more than a sale brings in. In the United States, promotional texts generally need the person's **prior written agreement** (the TCPA and state laws), must say how to stop, and have time-of-day limits; other countries and some states differ. **This is a tool, not legal advice, and Speakvora does not check that your list is real.** It only refuses to text anyone who is not on the list or who said STOP. Ask your own counsel before you start.

## Where things live
Everything is in your agent folder (`agent-state/sales.json`): the pages, the list, drafts and what was sent. Settings: Your agent, **Announce a sale**.
