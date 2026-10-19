# Knowledge

![Library, Knowledge](https://speakvora.com/assets/guide/library-knowledge.png)

![Add an answer](https://speakvora.com/assets/guide/sheet-addanswer.png)

*Screens come from a throwaway test setup; addresses and secrets shown are fake examples.*


The documents, pages and notes your AI answers customers from. Library, **Knowledge**.

## Add
* **Attach a file**: the usual way. In Library, Knowledge press **Choose a file** (or drag a file onto the box), or tap the paperclip in the Ask Speakvora box on Home. PDF, Word (.docx), text, Markdown, CSV, HTML or JSON, up to 3 MB. PDFs are read best when the free `pdftotext` tool is installed (Mac: `brew install poppler`; Linux: `poppler-utils`); without it simple PDFs still work, and a scanned PDF cannot be read: export it as text or Word, or paste the text.
* **Add a website**: your own site; the agent reads the page and a few more pages of the same site, once.
* **Paste text**: prices, menus, policies, opening hours. Plain sentences work best.

## How it is used
Each source is split into short passages and kept on this computer (`agent-state/knowledge/`). When a customer asks something, the agent finds the few passages that match and sends only those, with that one question, to your own AI. The AI must answer from them, copy prices and policies exactly and hand off when they do not cover the question. A price or phone number that appears in your knowledge counts as approved when an answer is checked; one that does not is never said.

## Privacy
* Everything is stored and searched locally; there is no index service.
* Passages that look like card numbers, ID numbers, passwords or long lists of email addresses are skipped when a source is added (the source shows how many).
* Do not upload customer records. Knowledge is for what your business says to everyone.
* Remove a source at any time (tap it, then Remove).

## Gaps
When your AI cannot answer a question, the question (with phone numbers and emails removed) appears under **Questions it could not answer** with a count. **Add answer** opens a note with the question; saving it clears the gap.

## Try it
Ask a question in **Try it** to see the answer your AI would give and which sources it used. Nothing is sent to a customer or recorded.
