# Several business locations in one dashboard (commercial licence)

If you run more than one branch, a commercial licence for two or more business locations adds a **Locations** button at the top of the dashboard. Click it to switch between your locations, see which ones need you, or open an overview of all of them.

## How it works
* **Every location runs its own agent**: its own bundle copy, phone number, settings and data. One branch's STOP list, limits and keys never mix with another's.
* **One dashboard to move between them.** This agent keeps a short list of your other locations and opens their dashboards through itself (your browser only talks to this agent). Each location's own dashboard keeps all its usual tabs; a bar at the top says where you are and takes you back.
* **Each location must be set up with its own business details.** Add the location, then open it from the menu and press **Set up** to fill in its name, hours, address and connections. Locations that are not set up yet show a "Set up" badge.
* **Each business location needs its own licence** (https://speakvora.com/pack-license). Ten or more locations: email speakvora@gmail.com for volume pricing.

## Turn it on
1. In your Speakvora account, open **My packs**, find your bundle (bought for two or more locations) and copy the **commercial licence code**.
2. In the dashboard open **Settings, Locations**, paste the code, then switch on the Locations menu and name this location.
3. **Name each agent in your account.** On speakvora.com/account press **Connect my agent**, type the location's name (for example Downtown) and get a code. Pair that location's agent with it. Its key shows in your keys list as "Agent (Downtown)", so you can find it and turn off just that location in one click.
4. For every other location: start its agent (`./sv-agent run`), copy the address and token it prints, and press **Add a location** here. If that agent runs on another computer, set `"dashboard": {"allow_remote": true}` in its agent.json and keep it on your private network.

## What the licence code does (and does not do)
The agent checks the code **offline** with Speakvora's public key; nothing is sent anywhere. It only turns the Locations menu on. Your bundle, its audio and every workflow work without a code. A code covers one bundle, a number of locations and a 12-month term; after the term ends the menu stays for 30 days so you can renew, then it hides until you paste a renewed code. The agent is open source, so this is an honest-use reminder, not copy protection.

## Security
Location access tokens are stored in `agent-state/secrets.json` (readable only by you), never in agent.json. The dashboard and the location pages open only on the computer running the agent (not through a tunnel or proxy).
