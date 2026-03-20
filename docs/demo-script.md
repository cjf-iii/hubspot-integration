# Demo Script — HubSpot Enrichment for Cast Iron Media

## Setup (before the demo)

1. Ensure `.env` has valid API keys
2. Run `cim setup` to configure HubSpot properties
3. Open HubSpot in browser, navigate to Companies

## The Demo (5 minutes)

### Beat 1: The Empty CRM (30 seconds)

- Show Rob the empty Companies list in HubSpot
- "Right now, adding a prospect means typing everything by hand — name, industry, spend, contacts. That takes 2 hours per prospect."

### Beat 2: One Command (60 seconds)

- In terminal, run: `cim demo "Culver's"`
- Watch the output: "Creating... Enriching... Generating AI brief... Writing back..."
- "10 seconds. That's it."

### Beat 3: The Enriched Record (2 minutes)

- Switch to HubSpot, refresh the Companies page
- Click into Culver's
- Walk through: Tier 2, QSR vertical, $65M spend, sports alignment 8/10
- Show the Contacts: VP Marketing, Media Director — with emails
- Show the Activity Timeline: "AI Prospect Brief" note
- Open the note — read the first paragraph of the brief
- Show the Task: "Review AI Brief — Culver's"
- "Your seller didn't research this. The system did it in 10 seconds."

### Beat 4: The Scale (30 seconds)

- "Multiply this by 221 prospects. That's 442 hours of research — done."
- "And this is just the enrichment. The same engine generates email drafts, meeting prep briefs, and proposals."

### Beat 5: The Visual (60 seconds)

- Open `visual/enrichment-demo.html` in browser
- Walk through the before/after transformation
- Show the pipeline flow at the bottom

## Key Messages

- "AI doesn't replace your sellers — it removes the busywork"
- "This works on HubSpot's free tier right now"
- "I can deploy this on your instance in weeks"
