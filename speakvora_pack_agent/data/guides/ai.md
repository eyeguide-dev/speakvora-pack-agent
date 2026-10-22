# Connect your own AI

Your AI answers what your rules do not (a detailed question, an unusual request), inside the agent's safeguards: it says it is an automated assistant, never takes card numbers or passwords, cannot refund or cancel, and connects your team when someone asks for a person. You pay the AI company directly; Speakvora adds nothing. Typical cost is a fraction of a cent per answer.

## Claude (Anthropic)
1. Go to console.anthropic.com and create an account, then add a small balance under Billing.
2. Open **API keys**, press **Create key** (make it inside your Default workspace), and copy it. It is shown once.
3. In the agent open **Connect, AI reasoning**, choose Claude, paste the key, and pick a fast model such as Haiku. Press Save and test.

## ChatGPT (OpenAI)
1. Go to platform.openai.com, add a balance under Billing, then open **API keys** and create one.
2. In the agent choose ChatGPT, paste the key, pick a fast model such as GPT-4o mini, and press Save and test.

## Another company or a model on your own computer
Choose Other. Enter the company's server address (for a local model such as Ollama: `http://localhost:11434/v1`), the model name written exactly as they do, and a key if they need one.

## Good to know
- Start with a low balance and a spending limit in the AI company's settings.
- What a workflow sends to the AI is limited to what that workflow chooses; read the AI privacy notes in Settings.
- If the test says the key is not tied to a workspace, create the key inside your Default workspace.

## Let your AI learn your business (it asks first)
Once your AI is connected, open **Home, Let your AI learn your business** (or Connect, Assistant, Learn my business). It works in steps, and each step that reads the web, sends text to your AI provider or spends your speech allowance waits for your OK:
1. **What it already knows.** Your business name, hours, address, industry and anything you already added. No network yet.
2. **Find your website.** Press "OK, search the web for my website": one web search (your business name and address) goes to DuckDuckGo from your computer, and you pick the site that is yours. Or type your address. No website? Skip this and add notes under Library, Knowledge.
3. **Read it.** Press "OK, read my website": the agent reads up to 40 pages of that one site on your computer (menu, products, services, hours, policies, a few PDFs), only where the site's robots.txt allows it, then sends the text to your own AI provider to organise it. Nothing goes to Speakvora. Emails and phone numbers are replaced before anything is sent.
4. **Is this accurate?** You see the hours and address it found (and where they differ from what you typed), a summary, the menu or price list, and the questions it can answer. Tick what to keep and press "Yes, this is accurate". Nothing is saved before that. Things the site does not say are listed, so you can add them.
5. **Phrases.** Press "OK, suggest phrases" and the agent proposes lines your business says often. Untick any you do not want, then record the rest: each is voiced once, then plays instantly and free.

Your AI then answers from what you approved and never goes beyond it. A site that builds its pages with scripts (some website builders) may show little text to a plain reader; the agent says what it could not read, and you can paste the menu under Library, Knowledge.
