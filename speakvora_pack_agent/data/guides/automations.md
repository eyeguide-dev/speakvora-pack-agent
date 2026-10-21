# Automations: phone menu, workflows and testing

Everything your agent does by itself lives in one place: the **Automations** tab. Here you build your phone menu ("press 1 for hours, 2 to book, 3 for Luli, 0 for a person"), make your own "when this happens, do this" automations, and test all of it by pretending to be a customer. Time: about 15 minutes. Cost: nothing extra.

## Before you start
- The agent is running and you can see the dashboard. Everything below happens in practice mode: nothing is sent, nobody is called.
- Settings, Your business details has your business name, opening hours and your **on-call phone** (the person key 0 connects to). Key 0 cannot connect anyone until that number is set.
- For a menu that customers can also *speak* to, connect your Speakvora key (Connect, Speakvora agent). Without it, callers use the keypad only.

## Step 1. Open the Automations tab
1. Press **Automations** in the top bar (on a phone it is the second icon at the bottom, next to Connect).
2. The three tiles at the top show how many automations are on, whether your phone menu is the standard one or your own, and whether sending is practice or live.
![The Automations tab on a computer](auto-overview.jpg)
3. Below them: **Phone menu** and **Test my agent** side by side, then **Your automations** and **Saved choices**.

## Step 2. Test what you have first
1. In **Test my agent**, type what a customer would text, for example "What are your hours?", and press **Send**. You see exactly what your agent would reply and why.
2. Under "Or pretend to phone your business", press **Call in**. You see what a caller hears. Then press a key (**Press 1**, **Press 3**) or type what a caller might say and press **Say it**.
3. Nothing is sent or dialled. A transfer shows "A real caller would now be connected to ..." and nothing more.

## Step 3. Build your phone menu
1. In the **Phone menu** card press **Build my own phone menu**.
2. **Greeting**: what callers hear first. You can write {{business}} and it becomes your business name.
3. **Keys**: each row is one key.
   - The first box is the key (0 to 9).
   - The text box finishes the sentence "Press 3 ...", for example `for opening hours`, `to book`, `for Luli`.
   - The last box is what the key does: tell your opening hours, say a message you write, take a callback request (your team is told), connect your staff phone, or connect a number you choose.
4. For a person or a department, choose **Connect them to a number I choose** and type the full phone number, with area code. It can be a person's mobile or a hunt group at your phone company.
![The phone menu editor with key 3 set to Luli](auto-menu-editor.jpg)
5. Press **Add a key** for more options (up to 9 keys plus 0). Press **Remove** to take one away.
6. Check **What callers hear** at the bottom of the same screen (in the picture above). It is the exact sentence, with your business name filled in.
7. Press **Save and switch on**. The card now shows your keys and the tile says **Custom**.
![The saved phone menu](auto-menu-saved.jpg)

Rules that keep callers safe:
- **Key 0 always reaches a person.** If you leave 0 out, the agent adds "0 to speak to a person". You cannot use 0 for anything else. Callers who say "person", "human" or "manager" are connected to a person too.
- Two misses in a row connect a person, so nobody is stuck in the menu.
- Do not put card numbers or passwords in the menu. The agent refuses them.

## Step 4. Voice it (optional)
Until you do this, callers hear your words in your phone provider's voice (or the computer's voice on an office phone connection). Press **Voice it in my bundle's voice** at the bottom of the editor to have Speakvora speak the greeting in your bundle's voice. It needs your Speakvora key and costs a few characters, once per line.

## Step 5. Test the new menu
1. Back in **Test my agent**, press **Call in**: you hear your new greeting.
2. Press each key and read what happens. Press 3 shows the number it would connect.
3. Type "can I talk to Luli" in the say box: spoken names from your menu work too.
![Pretending to call: pressing 3 connects the number you chose](auto-test-call.jpg)

## Step 6. Make your own automation
1. In **Your automations** press **New workflow**.
2. Choose **When this happens** (a customer texts a word, something happens in your app, a booking is coming up, or a time of day), then **Do this** (reply, text the customer, tell your team on Slack or Teams, or email someone).
3. Type your message. You can use details such as {{business}} or {{customer.name}}; the box tells you which ones fit.
4. Press **Save**. It is switched on. Use the switch in the list to turn it off later.
![The workflow builder](auto-workflow.jpg)
5. The ready-made automations for your industry are under **Show the ready-made automations**. Switch on the ones you want. A yellow "Needs" line says which app to connect first (Connect tab).

## Step 7. Go live
1. When everything above looks right, press **Go live** (on the Automations tab, or Settings).
2. The agent checks that your business details, a connected service and your automations have what they need. Fix anything it lists, then switch on sending.
3. Practice mode stays one switch away: Settings, Go live, **Back to practice mode**.

## On a phone
The same tab works on a phone: the tiles shrink, the cards stack, and the editor opens as a sheet from the bottom.
![The Automations tab on a phone](auto-mobile.jpg)

## Good to know
- Your phone menu works the same on every way callers can reach the agent: Twilio numbers and an existing office phone system.
- On an office phone system callers can speak their choice when the agent has your Speakvora key; the agent hears them until they pause, turns the words into text with Speakvora's speech-to-text (about $0.0015 a minute, audio not kept), and then does what the matching key does.
- Speaking is English only for now. The keypad works in every language.
- A transfer goes only to a number you typed. In practice mode no call is placed.
- **On an office phone connection, use an extension** (like 202) for a department. Callers are handed to your phone system, which connects them. A full outside number works only if your phone system knows how to dial it. On Twilio, use a full phone number: an extension is skipped there and the caller hears a polite message.
- On an office phone connection a custom greeting is spoken with the computer's own voice (Mac and many Linux systems have one). If the computer has none, the agent plays the bundle's recorded standard menu until you voice your greeting with Voice it in my bundle's voice.
- Switch back any time: **Use the standard menu** restores the bundle's menu. Your custom menu is saved separately, so a bundle update never overwrites it.
- Stuck? Press Full Guide on the connection you are setting up, or see the other guides in Connect.
