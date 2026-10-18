# Speech generation, caching and saving money

Your agent can say three kinds of things. Only one of them costs money, and only the first time.

| What it says | Cost |
|---|---|
| A **recorded line** from your bundle (hours, order ready, reminders...) | Free, instant, works offline |
| A line **you added** or an **instant answer** you wrote | Voiced once (a fraction of a cent), then free and instant forever |
| A **new sentence** your AI writes live | Voiced once, kept 30 days on your computer, so the same sentence again is free |
Your AI company also charges per answer (a few hundred tokens, usually a fraction of a cent). Twilio charges for calls, texts and its speech recognition. Speakvora charges nothing per message, per minute or per call. Speakvora voicing is $3 per million characters (library voices) or $6 (your own voice): a 120-character answer is about **$0.0004**, so 1,000 brand-new answers cost about 40 cents, and repeats cost nothing.

## 1. Make sure speech generation is on
1. **Pair the agent**: speakvora.com/account, **Connect my agent**, then your local dashboard, **Connect** tab, **Speakvora agent**, type the code, **Pair** (see [connect-apps.md](connect-apps.md)). The paired key is what voices new lines.
2. **Test it**: Settings, **AI controls**, **Test my voice**. You should hear "This is a test of your voice" and read "Speech generation is on" with this month's live-voice use.
![Settings: Ask before sending, AI controls with Test my voice, preferences](https://speakvora.com/assets/guide/settings.png)
3. **Add a card** on speakvora.com/account (Settings, Billing). The free allowance (100,000 characters) plays stored sentences; generating new text needs a card. There is no monthly minimum: you pay only for what you use.
4. If the test says it cannot voice: the agent is not paired, or the account has no card, or your internet is down. The message says which.

## 2. Put the phrases you say most in your own library (the cheapest setup)
Spend two minutes once and the common answers cost nothing, forever.
1. **Library, Saved, Add your own phrases**: one phrase per line (greetings, "we are open until ten", "our address is...", "yes we take reservations"). Each is voiced once in your bundle's voice, then plays free and instantly, even offline.
![Library: saved phrases, search, Add your own phrases](https://speakvora.com/assets/guide/library-saved.png)
2. **Library, Knowledge, Add an answer**: write a question customers ask and the exact answer. When a customer asks that (or something close) your agent says your words **instantly with no AI call**: free for the AI, and voiced once.
![Add an answer: a question and your exact words](https://speakvora.com/assets/guide/sheet-addanswer.png)
3. **Questions it could not answer** (Library, Knowledge and Home, Insights) lists what customers asked that nothing covered. Press **Add answer** on the ones asked most: each one you add is instant and free from then on.
![Library, Knowledge: Try it, add knowledge, questions it could not answer](https://speakvora.com/assets/guide/library-knowledge.png)
4. **Let it learn by itself**: Settings, **AI controls**, **Built-in safeguards**: switch on **Add lines my AI repeats to my library automatically** and choose after how many repeats. A sentence your AI keeps saying becomes a saved library line (counted against your monthly new-lines budget).
![Built-in safeguards: limits, auto-add repeated lines, allowed actions](https://speakvora.com/assets/guide/sheet-safeguards.png)

## 3. Set your limits
In **Built-in safeguards** you choose: the most back-and-forth turns in one conversation, the longest call, the most AI replies per hour, and the **characters of new voiced lines per month** (a hard stop: when it is used up the agent plays recorded lines or the phone company's plain voice instead of voicing new ones). Start low and raise it when you see the numbers in **Home, Insights**.

## 4. Where the cached audio lives (and how to clear it)
* Your own library lines: `agent-state/learned/`.
* Live answers and the "let me check that" lines: `agent-state/audio-cache/` (files starting `talk_` and `keep_`).
Deleting these files is safe: anything missing is voiced again the next time it is needed (and costs once). Back up `agent-state/` to keep your library when you move computers.

## 5. A simple monthly routine
1. Open **Home, Insights**: look at **Questions it could not answer** and **Top topics**.
2. Add answers to the top questions (Library, Knowledge, Add an answer).
3. Add the phrases you keep typing into the Library.
4. Watch the **live voice used** line in **Test my voice**: if it keeps growing for the same sentences, add them as library lines so they are free.
