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
