# Tell your team in Microsoft Teams

The agent posts a message to a Teams channel. This uses a Teams workflow, so it needs Microsoft Teams from a work or school Microsoft 365 account (free personal Teams cannot create these).

## Steps
1. In Teams open the channel you want, press the three dots next to its name, and choose **Workflows**.
2. Search for **Post to a channel when a webhook request is received** and select it.
3. Name it, confirm your Teams connection, choose the team and channel, and press **Add workflow**.
4. Teams shows a **web address**. Copy it.
5. In the agent open **Connect, Microsoft Teams**, paste it as the workflow / webhook URL, and press **Send a test message**. It should appear in the channel.

## Good to know
- Messages are text only.
- Treat the address like a password: anyone with it can post to your channel. If it leaks, delete the workflow and make a new one.
- Menu names change as Microsoft updates Teams. If you cannot find Workflows, search the app for "webhook".
